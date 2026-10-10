"""Tests for experiments/tools/profile_dataset.py using small synthetic CSVs
generated inline (no downloads, no fixture files committed).

Run: python -m experiments.tests.test_profile_dataset
"""
import csv
import json
import shutil
import sys
import tempfile
from pathlib import Path

from experiments.tools.profile_dataset import main as profile_main

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if not condition:
        FAILURES.append(f"{label}: {detail}")


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def run_profile(input_path: Path, out_path: Path, extra_args: list[str] | None = None) -> int:
    args = ["--input", str(input_path), "--out", str(out_path)] + (extra_args or [])
    return profile_main(args)


# ---------------------------------------------------------------------------
# 1. Regression table
# ---------------------------------------------------------------------------

def test_regression_table() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        csv_path = tmp / "regression.csv"
        rows = [[i, i * 0.5, i * 1.5 + 2.0] for i in range(1, 51)]
        write_csv(csv_path, ["id", "feature1", "target"], rows)

        out_path = tmp / "profile.json"
        exit_code = run_profile(csv_path, out_path)
        check("regression.exit_code", exit_code == 0, exit_code)

        with open(out_path) as f:
            profile = json.load(f)

        check("regression.n_rows", profile["n_rows"] == 50, profile["n_rows"])
        check("regression.n_cols", profile["n_cols"] == 3, profile["n_cols"])
        check("regression.task_type", profile["target"]["task_type"] == "regression", profile["target"])
        check("regression.target_guessed", profile["target"]["guessed"] is True, profile["target"])
        check("regression.no_missing", profile["columns"]["feature1"]["missing_count"] == 0, profile["columns"]["feature1"])
        check("regression.class_balance_null", profile["class_balance"] is None, profile["class_balance"])
        check(
            "regression.leakage_detected",
            any("target" in h for h in profile["leakage_hints"]),
            profile["leakage_hints"],
        )
        check(
            "regression.correlated_pairs_found",
            len(profile["highly_correlated_pairs"]) > 0,
            profile["highly_correlated_pairs"],
        )
        check("regression.id_flagged", profile["columns"]["id"]["is_possible_id"] is True, profile["columns"]["id"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 2. Classification table with imbalance and a constant column
# ---------------------------------------------------------------------------

def test_classification_table_imbalance_and_constant() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        csv_path = tmp / "classification.csv"
        rows = []
        for i in range(100):
            label = "pos" if i < 90 else "neg"
            rows.append([i, "always_the_same", label])
        write_csv(csv_path, ["id", "const_col", "label"], rows)

        out_path = tmp / "profile.json"
        exit_code = run_profile(csv_path, out_path, ["--target", "label"])
        check("classification.exit_code", exit_code == 0, exit_code)

        with open(out_path) as f:
            profile = json.load(f)

        check("classification.task_type", profile["target"]["task_type"] == "classification", profile["target"])
        check("classification.target_not_guessed", profile["target"]["guessed"] is False, profile["target"])
        check(
            "classification.class_balance",
            profile["class_balance"] == {"pos": 90, "neg": 10},
            profile["class_balance"],
        )
        check("classification.constant_flagged", profile["columns"]["const_col"]["is_constant"] is True, profile["columns"]["const_col"])
        check(
            "classification.imbalance_warning",
            any("imbalance" in w for w in profile["warnings"]),
            profile["warnings"],
        )
        check(
            "classification.constant_warning",
            any("constant" in w and "const_col" in w for w in profile["warnings"]),
            profile["warnings"],
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 3. Missing values and an ID column
# ---------------------------------------------------------------------------

def test_missing_values_and_id_column() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        csv_path = tmp / "missing_id.csv"
        rows = []
        for i in range(40):
            user_id = f"U{i:05d}"
            age = "" if i % 5 == 0 else str(20 + (i % 50))
            score = i * 2.0
            rows.append([user_id, age, score])
        write_csv(csv_path, ["user_id", "age", "score"], rows)

        out_path = tmp / "profile.json"
        exit_code = run_profile(csv_path, out_path, ["--target", "score"])
        check("missing_id.exit_code", exit_code == 0, exit_code)

        with open(out_path) as f:
            profile = json.load(f)

        check("missing_id.id_flagged", profile["columns"]["user_id"]["is_possible_id"] is True, profile["columns"]["user_id"])
        expected_missing = sum(1 for i in range(40) if i % 5 == 0)
        check(
            "missing_id.missing_count",
            profile["columns"]["age"]["missing_count"] == expected_missing,
            (profile["columns"]["age"]["missing_count"], expected_missing),
        )
        check(
            "missing_id.missing_fraction",
            abs(profile["columns"]["age"]["missing_fraction"] - expected_missing / 40) < 1e-9,
            profile["columns"]["age"]["missing_fraction"],
        )
        check(
            "missing_id.id_warning",
            any("ID column" in w and "user_id" in w for w in profile["warnings"]),
            profile["warnings"],
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 4. Bad file
# ---------------------------------------------------------------------------

def test_bad_file_nonexistent() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        out_path = tmp / "profile.json"
        exit_code = run_profile(tmp / "does_not_exist.csv", out_path)
        check("bad_file.nonexistent_nonzero_exit", exit_code != 0, exit_code)
        check("bad_file.no_output_written", not out_path.exists(), "a profile should not be written on failure")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_bad_file_empty() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        csv_path = tmp / "empty.csv"
        csv_path.write_text("")
        out_path = tmp / "profile.json"
        exit_code = run_profile(csv_path, out_path)
        check("bad_file.empty_nonzero_exit", exit_code != 0, exit_code)
        check("bad_file.empty_no_output_written", not out_path.exists(), "a profile should not be written on failure")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_bad_file_unsupported_extension() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        bad_path = tmp / "data.txt"
        bad_path.write_text("a,b\n1,2\n")
        out_path = tmp / "profile.json"
        exit_code = run_profile(bad_path, out_path)
        check("bad_file.unsupported_ext_nonzero_exit", exit_code != 0, exit_code)
        check("bad_file.unsupported_ext_no_output_written", not out_path.exists(), "a profile should not be written on failure")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Extra: sampling behaviour (--max-rows)
# ---------------------------------------------------------------------------

def test_max_rows_sampling() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        csv_path = tmp / "big.csv"
        rows = [[i, i * 2] for i in range(500)]
        write_csv(csv_path, ["a", "b"], rows)

        out_path = tmp / "profile.json"
        exit_code = run_profile(csv_path, out_path, ["--max-rows", "50"])
        check("sampling.exit_code", exit_code == 0, exit_code)

        with open(out_path) as f:
            profile = json.load(f)

        check("sampling.sampled_flag", profile["file"]["sampled"] is True, profile["file"])
        check("sampling.rows_capped", profile["n_rows"] == 50, profile["n_rows"])
        check(
            "sampling.warning_present",
            any("sampled" in w for w in profile["warnings"]),
            profile["warnings"],
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    tests = [
        test_regression_table,
        test_classification_table_imbalance_and_constant,
        test_missing_values_and_id_column,
        test_bad_file_nonexistent,
        test_bad_file_empty,
        test_bad_file_unsupported_extension,
        test_max_rows_sampling,
    ]
    for t in tests:
        print(f"running {t.__name__} ...")
        t()

    if FAILURES:
        print(f"FAILED {len(FAILURES)} checks:")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print(f"ALL CHECKS PASSED ({len(tests)} scenarios)")


if __name__ == "__main__":
    main()
