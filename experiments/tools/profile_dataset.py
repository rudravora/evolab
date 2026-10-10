"""Profile a tabular dataset (CSV, TSV or Parquet) and write a profile.json.

Runs as a worker python_script job (ARCHITECTURE.md section 5, API.md
section 9): the worker's argv is `["python", "profile_dataset.py", ...]`
inside the per-project jail; this script itself does not know about jails or
jobs, it just reads one input file and writes one output file.

Usage:
    python profile_dataset.py --input <path> --out <profile.json> \
        [--target <column>] [--max-rows N]

--max-rows (default 200000): read at most this many rows. For CSV/TSV this
reads in chunks and stops once the cap is hit (no full-file load for huge
files); for Parquet, row-group-aware chunked reads are used if the engine
supports it, falling back to a full read then truncating if not an inherent
chunk interface is available (noted in the profile's `sampled` flag either
way). If the cap was hit, `file.sampled` is true and `file.rows_read` /
`n_rows` reflect the sampled count, not the full file's row count.

Security: the dataset is untrusted input (ARCHITECTURE.md section 6, prompt
injection / untrusted-data handling). This script never calls eval(), exec(),
pickle.load(), pandas.read_pickle(), or any other mechanism that would
execute code found inside the file. CSV/TSV parsing uses pandas' default C
parser (no formula evaluation, unlike opening the file in a spreadsheet
application); Parquet parsing uses pyarrow's binary columnar reader. Column
*names* and *string cell values* found in the data are treated purely as
data: used only as dict keys/string values in the JSON output, never
interpreted, formatted into a path, or passed to a shell.

Output profile.json keys (all always present unless noted):
  file:
    path, format ("csv"|"tsv"|"parquet"), bytes, sampled (bool),
    rows_read (rows actually read, <= n_rows_total if sampled)
  n_rows: int (same as file.rows_read)
  n_cols: int
  columns: { <column name>: {
      dtype: str (pandas dtype name, e.g. "int64", "float64", "object", "bool")
      missing_count: int
      missing_fraction: float
      n_unique: int
      min, max, mean, std: float|null (numeric columns only, null otherwise)
      top_values: [[value, count], ...] (categorical/object columns only,
        up to 10 entries, empty list for numeric columns)
      is_constant: bool (exactly one distinct non-missing value)
      is_near_constant: bool (one value covers >= 0.99 of non-missing rows,
        and the column is not already flagged is_constant)
      is_possible_id: bool (n_unique == n_rows, i.e. every non-missing value
        is unique -- a weak heuristic, see warnings for caveats)
  } }
  duplicate_row_count: int (exact full-row duplicates, among rows read)
  target: { column: str|null, task_type: "classification"|"regression"|"unknown",
            guessed: bool (true if --target was not given and this is a guess) }
  class_balance: { <class label as str>: count } | null (only when task_type
    is "classification")
  highly_correlated_pairs: [[colA, colB, corr], ...] (numeric column pairs
    with |Pearson r| > 0.95, excluding a column against itself)
  leakage_hints: [str, ...] (feature(s) identical to or perfectly correlated
    (|r| == 1.0, or exact value match) with the target)
  warnings: [str, ...] (anything the profile wants to flag: sampling,
    unreadable columns, heuristic caveats, etc.)

Exits 0 on success (prints one summary line to stdout), nonzero with one
clear line on stderr on failure (bad path, unreadable format, empty file).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

DEFAULT_MAX_ROWS = 200_000
TOP_VALUES_LIMIT = 10
CORRELATION_THRESHOLD = 0.95
NEAR_CONSTANT_FRACTION = 0.99
CSV_CHUNK_ROWS = 50_000


class ProfileError(Exception):
    """Any error that should produce a one-line message on stderr and a
    nonzero exit, rather than a raw traceback."""


def detect_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".tsv":
        return "tsv"
    if suffix == ".parquet":
        return "parquet"
    raise ProfileError(f"unsupported file extension {suffix!r} (expected .csv, .tsv or .parquet): {path}")


def read_dataset(path: Path, fmt: str, max_rows: int) -> tuple[pd.DataFrame, bool]:
    """Returns (dataframe, sampled). sampled is True if max_rows capped the
    read short of the full file.
    """
    if fmt in ("csv", "tsv"):
        sep = "," if fmt == "csv" else "\t"
        chunks = []
        rows_so_far = 0
        sampled = False
        try:
            reader = pd.read_csv(path, sep=sep, chunksize=CSV_CHUNK_ROWS, low_memory=False)
            for chunk in reader:
                remaining = max_rows - rows_so_far
                if remaining <= 0:
                    sampled = True
                    break
                if len(chunk) > remaining:
                    chunk = chunk.iloc[:remaining]
                    sampled = True
                chunks.append(chunk)
                rows_so_far += len(chunk)
                if rows_so_far >= max_rows:
                    # Check whether more rows exist beyond this chunk boundary.
                    try:
                        next(reader)
                        sampled = True
                    except StopIteration:
                        pass
                    break
        except pd.errors.EmptyDataError as exc:
            raise ProfileError(f"file has no parseable data: {path}") from exc
        except (pd.errors.ParserError, UnicodeDecodeError, OSError) as exc:
            raise ProfileError(f"could not parse {fmt.upper()} file: {exc}") from exc
        if not chunks:
            raise ProfileError(f"file has no rows: {path}")
        df = pd.concat(chunks, ignore_index=True)
        return df, sampled

    if fmt == "parquet":
        try:
            full_df = pd.read_parquet(path)
        except ImportError as exc:
            raise ProfileError(
                "reading Parquet requires pyarrow (or fastparquet) to be installed"
            ) from exc
        except (OSError, ValueError) as exc:
            raise ProfileError(f"could not parse Parquet file: {exc}") from exc
        if len(full_df) == 0:
            raise ProfileError(f"file has no rows: {path}")
        if len(full_df) > max_rows:
            return full_df.iloc[:max_rows].reset_index(drop=True), True
        return full_df, False

    raise ProfileError(f"unsupported format: {fmt!r}")


def profile_column(series: pd.Series, n_rows: int) -> dict:
    missing_count = int(series.isna().sum())
    non_missing = series.dropna()
    n_unique = int(non_missing.nunique())

    dtype_str = str(series.dtype)
    is_numeric = pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series)

    col_info = {
        "dtype": dtype_str,
        "missing_count": missing_count,
        "missing_fraction": (missing_count / n_rows) if n_rows else 0.0,
        "n_unique": n_unique,
        "min": None,
        "max": None,
        "mean": None,
        "std": None,
        "top_values": [],
        "is_constant": False,
        "is_near_constant": False,
        "is_possible_id": n_unique == n_rows and n_rows > 0,
    }

    if len(non_missing) == 0:
        return col_info

    if is_numeric:
        col_info["min"] = float(non_missing.min())
        col_info["max"] = float(non_missing.max())
        col_info["mean"] = float(non_missing.mean())
        col_info["std"] = float(non_missing.std()) if len(non_missing) > 1 else 0.0
    else:
        value_counts = non_missing.astype(str).value_counts().head(TOP_VALUES_LIMIT)
        col_info["top_values"] = [[str(v), int(c)] for v, c in value_counts.items()]

    if n_unique == 1:
        col_info["is_constant"] = True
    else:
        top_fraction = non_missing.value_counts(normalize=True).iloc[0]
        if top_fraction >= NEAR_CONSTANT_FRACTION:
            col_info["is_near_constant"] = True

    return col_info


def guess_target_and_task(df: pd.DataFrame, target: str | None) -> tuple[str | None, str, bool]:
    """Returns (target_column, task_type, guessed)."""
    if target is not None:
        if target not in df.columns:
            raise ProfileError(f"--target column {target!r} not found in dataset columns: {list(df.columns)}")
        return target, _infer_task_type(df[target]), False

    candidate_names = ("target", "label", "class", "y")
    for name in candidate_names:
        for col in df.columns:
            if col.lower() == name:
                return col, _infer_task_type(df[col]), True

    last_col = df.columns[-1] if len(df.columns) > 0 else None
    if last_col is None:
        return None, "unknown", True
    return last_col, _infer_task_type(df[last_col]), True


def _infer_task_type(series: pd.Series) -> str:
    """Heuristic only (no doc specifies this precisely -- see assumptions).
    Non-numeric -> classification. Numeric with very few distinct values
    relative to the row count (and few enough in absolute terms that it
    looks like a label set, not a sampled continuum) -> classification.
    Otherwise -> regression.
    """
    non_missing = series.dropna()
    n_rows = len(non_missing)
    if n_rows == 0:
        return "unknown"
    is_numeric = pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series)
    n_unique = non_missing.nunique()
    if not is_numeric:
        return "classification"
    # A numeric column is only "classification-shaped" if it both repeats
    # values a lot (low unique ratio) AND has a small absolute label count --
    # a tiny regression target (n_rows=5, all distinct) must not qualify.
    unique_ratio = n_unique / n_rows
    if n_unique <= 20 and unique_ratio <= 0.5:
        return "classification"
    return "regression"


def compute_class_balance(df: pd.DataFrame, target_col: str) -> dict:
    counts = df[target_col].astype(str).value_counts()
    return {str(k): int(v) for k, v in counts.items()}


def compute_correlated_pairs(df: pd.DataFrame) -> list:
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])]
    if len(numeric_cols) < 2:
        return []
    corr = df[numeric_cols].corr(numeric_only=True)
    pairs = []
    for i, col_a in enumerate(numeric_cols):
        for col_b in numeric_cols[i + 1 :]:
            r = corr.loc[col_a, col_b]
            if pd.isna(r):
                continue
            if abs(r) > CORRELATION_THRESHOLD:
                pairs.append([col_a, col_b, float(r)])
    return pairs


def compute_leakage_hints(df: pd.DataFrame, target_col: str | None) -> list[str]:
    if target_col is None or target_col not in df.columns:
        return []
    hints = []
    target_series = df[target_col]
    target_is_numeric = pd.api.types.is_numeric_dtype(target_series) and not pd.api.types.is_bool_dtype(target_series)

    for col in df.columns:
        if col == target_col:
            continue
        other = df[col]
        if other.equals(target_series):
            hints.append(f"column {col!r} is identical to the target {target_col!r}")
            continue
        if target_is_numeric and pd.api.types.is_numeric_dtype(other) and not pd.api.types.is_bool_dtype(other):
            paired = pd.concat([other, target_series], axis=1).dropna()
            if len(paired) > 1:
                r = paired.iloc[:, 0].corr(paired.iloc[:, 1])
                if pd.notna(r) and abs(r) >= 0.999:
                    hints.append(f"column {col!r} is near-perfectly correlated with target {target_col!r} (r={r:.4f})")
    return hints


def build_profile(path: Path, fmt: str, df: pd.DataFrame, sampled: bool, target_arg: str | None) -> dict:
    n_rows, n_cols = len(df), len(df.columns)
    warnings: list[str] = []

    if sampled:
        warnings.append(f"input was sampled: only the first {n_rows} rows were read")

    columns_profile = {}
    for col in df.columns:
        try:
            columns_profile[str(col)] = profile_column(df[col], n_rows)
        except Exception as exc:  # a single bad column should not abort the whole profile
            warnings.append(f"could not profile column {col!r}: {exc}")
            columns_profile[str(col)] = {
                "dtype": str(df[col].dtype),
                "missing_count": None,
                "missing_fraction": None,
                "n_unique": None,
                "min": None,
                "max": None,
                "mean": None,
                "std": None,
                "top_values": [],
                "is_constant": False,
                "is_near_constant": False,
                "is_possible_id": False,
            }

    duplicate_row_count = int(df.duplicated().sum())

    target_col, task_type, guessed = guess_target_and_task(df, target_arg)
    if guessed:
        warnings.append(f"--target not given; guessed target column {target_col!r} ({task_type})")

    class_balance = None
    if task_type == "classification" and target_col is not None:
        class_balance = compute_class_balance(df, target_col)
        if len(class_balance) > 1:
            counts = list(class_balance.values())
            if max(counts) / max(1, min(counts)) >= 4:
                warnings.append("class imbalance: largest class is >= 4x the smallest")

    highly_correlated_pairs = compute_correlated_pairs(df)
    leakage_hints = compute_leakage_hints(df, target_col)
    if leakage_hints:
        warnings.append("possible target leakage detected -- see leakage_hints")

    for col_name, info in columns_profile.items():
        if info.get("is_constant"):
            warnings.append(f"column {col_name!r} is constant")
        elif info.get("is_near_constant"):
            warnings.append(f"column {col_name!r} is near-constant")
        if info.get("is_possible_id") and col_name != target_col:
            warnings.append(f"column {col_name!r} looks like an ID column (all values unique)")

    return {
        "file": {
            "path": str(path),
            "format": fmt,
            "bytes": path.stat().st_size,
            "sampled": sampled,
            "rows_read": n_rows,
        },
        "n_rows": n_rows,
        "n_cols": n_cols,
        "columns": columns_profile,
        "duplicate_row_count": duplicate_row_count,
        "target": {"column": target_col, "task_type": task_type, "guessed": guessed},
        "class_balance": class_balance,
        "highly_correlated_pairs": highly_correlated_pairs,
        "leakage_hints": leakage_hints,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Profile a tabular dataset (CSV, TSV or Parquet)")
    parser.add_argument("--input", required=True, help="path to the dataset file")
    parser.add_argument("--out", required=True, help="path to write profile.json")
    parser.add_argument("--target", default=None, help="target column name; guessed if omitted")
    parser.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS, dest="max_rows")
    args = parser.parse_args(argv)

    try:
        input_path = Path(args.input)
        if not input_path.exists():
            raise ProfileError(f"input file does not exist: {input_path}")
        if not input_path.is_file():
            raise ProfileError(f"input path is not a file: {input_path}")

        fmt = detect_format(input_path)
        df, sampled = read_dataset(input_path, fmt, args.max_rows)
        profile = build_profile(input_path, fmt, df, sampled, args.target)
    except ProfileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error: unexpected failure profiling {args.input}: {exc}", file=sys.stderr)
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(profile, f, indent=2, sort_keys=True)
        f.write("\n")

    sampled_note = " (sampled)" if profile["file"]["sampled"] else ""
    print(
        f"profiled {input_path.name}: {profile['n_rows']} rows, {profile['n_cols']} cols, "
        f"target={profile['target']['column']!r} ({profile['target']['task_type']}), "
        f"{len(profile['warnings'])} warning(s){sampled_note} -> {out_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
