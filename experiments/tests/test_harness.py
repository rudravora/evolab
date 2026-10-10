"""Harness tests: the _dummy paper runs twice with the same seed and
produces identical metrics; schema validation fails on bad result files.

Run: python -m experiments.tests.test_harness
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

from experiments.harness import result_schema
from experiments.harness.run import main as harness_main

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if not condition:
        FAILURES.append(f"{label}: {detail}")


def run_dummy(out_dir: Path, *, method: str = "linear", seed: int = 0) -> dict:
    exit_code = harness_main(
        [
            "--paper",
            "_dummy",
            "--task",
            "toy_regression",
            "--method",
            method,
            "--seed",
            str(seed),
            "--budget-min",
            "1",
            "--out",
            str(out_dir),
        ]
    )
    result_files = list(out_dir.glob("*.json"))
    check(f"run_dummy[{method},{seed}].exit_code", exit_code == 0, f"got {exit_code}")
    check(f"run_dummy[{method},{seed}].one_file_written", len(result_files) == 1, result_files)
    with open(result_files[0]) as f:
        data = json.load(f)
    return data


def test_same_seed_same_metrics() -> None:
    tmp1 = Path(tempfile.mkdtemp())
    tmp2 = Path(tempfile.mkdtemp())
    try:
        result1 = run_dummy(tmp1, method="linear", seed=42)
        result2 = run_dummy(tmp2, method="linear", seed=42)
        check("same_seed.status_done", result1["status"] == "done" and result2["status"] == "done", (result1, result2))
        check(
            "same_seed.metrics_identical",
            result1["metrics"] == result2["metrics"],
            f"run1={result1['metrics']} run2={result2['metrics']}",
        )
        check(
            "same_seed.param_count_identical",
            result1["param_count"] == result2["param_count"],
            (result1["param_count"], result2["param_count"]),
        )
        check("same_seed.run_ids_differ", result1["run_id"] != result2["run_id"], "run_id should be unique per run")
    finally:
        shutil.rmtree(tmp1, ignore_errors=True)
        shutil.rmtree(tmp2, ignore_errors=True)


def test_different_seed_can_differ() -> None:
    # Not a strict requirement, but a sanity check that seeding is actually
    # doing something (noise_std > 0 in _dummy's default config).
    tmp1 = Path(tempfile.mkdtemp())
    tmp2 = Path(tempfile.mkdtemp())
    try:
        result1 = run_dummy(tmp1, method="linear", seed=1)
        result2 = run_dummy(tmp2, method="linear", seed=2)
        check(
            "different_seed.metrics_can_differ",
            result1["metrics"] != result2["metrics"],
            "metrics were identical across different seeds -- seeding may not be wired correctly",
        )
    finally:
        shutil.rmtree(tmp1, ignore_errors=True)
        shutil.rmtree(tmp2, ignore_errors=True)


def test_two_methods_both_run() -> None:
    tmp1 = Path(tempfile.mkdtemp())
    tmp2 = Path(tempfile.mkdtemp())
    try:
        linear_result = run_dummy(tmp1, method="linear", seed=0)
        mean_result = run_dummy(tmp2, method="mean", seed=0)
        check("two_methods.linear_done", linear_result["status"] == "done", linear_result)
        check("two_methods.mean_done", mean_result["status"] == "done", mean_result)
        check("two_methods.different_param_counts", linear_result["param_count"] != mean_result["param_count"], (linear_result, mean_result))
    finally:
        shutil.rmtree(tmp1, ignore_errors=True)
        shutil.rmtree(tmp2, ignore_errors=True)


def test_nonexistent_paper_fails_cleanly() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        exit_code = harness_main(
            [
                "--paper",
                "_does_not_exist",
                "--task",
                "x",
                "--method",
                "y",
                "--seed",
                "0",
                "--budget-min",
                "1",
                "--out",
                str(tmp),
            ]
        )
        check("nonexistent_paper.nonzero_exit", exit_code != 0, exit_code)
        check("nonexistent_paper.no_file_written", len(list(tmp.glob("*.json"))) == 0, "a result file should not be written for a load failure")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_failing_method_writes_failed_result() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        exit_code = harness_main(
            [
                "--paper",
                "_dummy",
                "--task",
                "toy_regression",
                "--method",
                "bogus_method_name",
                "--seed",
                "0",
                "--budget-min",
                "1",
                "--out",
                str(tmp),
            ]
        )
        check("failing_method.nonzero_exit", exit_code != 0, exit_code)
        result_files = list(tmp.glob("*.json"))
        check("failing_method.file_still_written", len(result_files) == 1, result_files)
        with open(result_files[0]) as f:
            data = json.load(f)
        check("failing_method.status_failed", data["status"] == "failed", data)
        check("failing_method.has_error_signature", bool(data.get("error_signature")), data)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------

VALID_RESULT = {
    "run_id": "run_abc123",
    "paper_slug": "_dummy",
    "task": "toy_regression",
    "method": "linear",
    "config": {"seed": 0},
    "seed": 0,
    "metrics": {"test_mse": 0.01},
    "train_seconds": 0.5,
    "software_versions": {"python": "3.14.7"},
    "status": "done",
    "param_count": 3,
    "error_signature": None,
}


def test_schema_accepts_valid_result() -> None:
    try:
        result_schema.validate(VALID_RESULT)
    except result_schema.ValidationError as exc:
        check("schema.valid_result_accepted", False, str(exc))
        return
    check("schema.valid_result_accepted", True)


def test_schema_rejects_missing_field() -> None:
    bad = dict(VALID_RESULT)
    del bad["metrics"]
    try:
        result_schema.validate(bad)
        check("schema.missing_field_rejected", False, "validate() did not raise on a missing required field")
    except result_schema.ValidationError:
        check("schema.missing_field_rejected", True)


def test_schema_rejects_bad_status() -> None:
    bad = dict(VALID_RESULT)
    bad["status"] = "not_a_real_status"
    try:
        result_schema.validate(bad)
        check("schema.bad_status_rejected", False, "validate() did not raise on an invalid status value")
    except result_schema.ValidationError:
        check("schema.bad_status_rejected", True)


def test_schema_rejects_non_numeric_metric() -> None:
    bad = dict(VALID_RESULT)
    bad["metrics"] = {"test_mse": "not a number"}
    try:
        result_schema.validate(bad)
        check("schema.non_numeric_metric_rejected", False, "validate() did not raise on a non-numeric metric value")
    except result_schema.ValidationError:
        check("schema.non_numeric_metric_rejected", True)


def test_schema_rejects_failed_without_error_signature() -> None:
    bad = dict(VALID_RESULT)
    bad["status"] = "failed"
    bad["error_signature"] = None
    try:
        result_schema.validate(bad)
        check("schema.failed_without_signature_rejected", False, "validate() did not raise when status=failed but error_signature is missing")
    except result_schema.ValidationError:
        check("schema.failed_without_signature_rejected", True)


def test_example_result_file_is_valid() -> None:
    example_path = Path(__file__).resolve().parent.parent / "harness" / "example_result.json"
    with open(example_path) as f:
        data = json.load(f)
    try:
        result_schema.validate(data)
        check("schema.example_file_valid", True)
    except result_schema.ValidationError as exc:
        check("schema.example_file_valid", False, str(exc))


def main() -> None:
    tests = [
        test_same_seed_same_metrics,
        test_different_seed_can_differ,
        test_two_methods_both_run,
        test_nonexistent_paper_fails_cleanly,
        test_failing_method_writes_failed_result,
        test_schema_accepts_valid_result,
        test_schema_rejects_missing_field,
        test_schema_rejects_bad_status,
        test_schema_rejects_non_numeric_metric,
        test_schema_rejects_failed_without_error_signature,
        test_example_result_file_is_valid,
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
