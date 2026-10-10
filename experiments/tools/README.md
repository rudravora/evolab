# experiments/tools/

## profile_dataset.py

Profiles a tabular dataset (CSV, TSV or Parquet) and writes a `profile.json`.
Runs as a worker `python_script` job (ARCHITECTURE.md section 5, API.md
section 9) — the Env and Data Engineer agent creates a job whose argv runs
this script, then reads back the profile to decide on a target column, task
type, and whether to flag a leakage or data-quality issue for re-planning
(WORKFLOW.md).

```bash
python profile_dataset.py --input data.csv --out profile.json
python profile_dataset.py --input data.parquet --out profile.json --target label --max-rows 50000
```

| Flag | Required | Default | Meaning |
|---|---|---|---|
| `--input` | yes | — | path to the dataset file (`.csv`, `.tsv` or `.parquet`) |
| `--out` | yes | — | path to write the profile JSON |
| `--target` | no | guessed | target column name; if omitted, the script guesses one and sets `target.guessed: true` |
| `--max-rows` | no | 200000 | read at most this many rows; CSV/TSV read in chunks and stop early, Parquet is read fully then truncated. If the file has more rows than this, `file.sampled` is `true` in the output |

Exits `0` on success and prints one summary line to stdout. Exits nonzero
with one line on stderr on failure (missing file, unsupported extension,
unparseable file, empty file).

**Security:** the dataset is untrusted input. This script never calls
`eval()`, `exec()`, `pickle.load()`, `pandas.read_pickle()`, or anything else
that would execute code found inside the file — CSV/TSV goes through
pandas' C parser, Parquet through pyarrow's binary columnar reader. Column
names and string values found in the data are only ever used as plain
strings (dict keys, JSON string values); they are never interpreted,
formatted into a shell command, or used to build a filesystem path.

### Output schema (`profile.json`)

```
file: { path, format: "csv"|"tsv"|"parquet", bytes, sampled: bool, rows_read }
n_rows: int                      # same as file.rows_read
n_cols: int
columns: {
  <column name>: {
    dtype: str                   # pandas dtype name
    missing_count: int
    missing_fraction: float
    n_unique: int
    min, max, mean, std: float | null     # numeric columns only
    top_values: [[value, count], ...]     # categorical/object columns only, up to 10
    is_constant: bool            # exactly one distinct non-missing value
    is_near_constant: bool       # one value covers >= 99% of non-missing rows
    is_possible_id: bool         # every non-missing value is unique (weak heuristic)
  }
}
duplicate_row_count: int         # exact full-row duplicates, among rows read
target: {
  column: str | null
  task_type: "classification" | "regression" | "unknown"
  guessed: bool                  # true if --target was not given
}
class_balance: { <label>: count } | null   # only when task_type == "classification"
highly_correlated_pairs: [[colA, colB, corr], ...]   # numeric pairs, |r| > 0.95
leakage_hints: [str, ...]        # features identical to or near-perfectly correlated with the target
warnings: [str, ...]
```

See the docstring at the top of `profile_dataset.py` for the exact rules
behind each field (constant/near-constant thresholds, the task-type guess
heuristic, etc.) — this README summarizes it, the docstring is the source
of truth if they ever drift.

A full example is in `shared/examples/worker/profile_dataset_result.json`.

### Known heuristic limitations (see the module docstring and the task's own report)

- `is_possible_id` is a pure uniqueness check — a genuinely continuous
  numeric feature (e.g. a precise timestamp or measurement) can trip it even
  though it is not an identifier. Treat it as a hint, not a verdict.
- The classification/regression guess for a numeric target without
  `--target` looks at how many distinct values it has relative to the row
  count; on an unusual dataset (e.g. a regression target that happens to
  repeat a lot, or a classification label set with hundreds of classes) it
  can guess wrong. Passing `--target` explicitly always wins.
- Leakage detection only catches exact matches and near-perfect (|r| >=
  0.999) linear correlation with the target. Non-linear leakage, or leakage
  spread across several features jointly, is not detected.
