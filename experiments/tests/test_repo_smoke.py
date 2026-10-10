"""Tests for experiments/tools/repo_smoke.py using tiny synthetic repos
built inline in a temp dir (no downloads, no network).

Run: python -m experiments.tests.test_repo_smoke
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

from experiments.tools.repo_smoke import main as smoke_main

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if not condition:
        FAILURES.append(f"{label}: {detail}")


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def run_smoke(repo: Path, out: Path, extra_args: list[str] | None = None) -> int:
    args = ["--repo", str(repo), "--out", str(out)] + (extra_args or [])
    return smoke_main(args)


# ---------------------------------------------------------------------------
# 1. Clean repo: pinned deps, README, LICENSE, tests, no missing imports
# ---------------------------------------------------------------------------

def test_clean_repo() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        write(tmp / "requirements.txt", "numpy==1.26.4\n")
        write(tmp / "README.md", "# clean repo\n")
        write(tmp / "LICENSE", "MIT\n")
        write(tmp / "mypkg" / "__init__.py", "import numpy\nimport os\n")
        write(tmp / "tests" / "test_basic.py", "def test_ok():\n    assert True\n")

        out = tmp / "smoke.json"
        exit_code = run_smoke(tmp, out)
        check("clean.exit_code", exit_code == 0, exit_code)

        with open(out) as f:
            result = json.load(f)

        check("clean.mode", result["mode"] == "static", result)
        check("clean.project_type", result["project_type"] == "python", result)
        check("clean.dependency_files", result["dependency_files"] == ["requirements.txt"], result)
        check("clean.no_unpinned", result["unpinned"] == [], result)
        check("clean.no_missing_deps", result["missing_declared_deps"] == [], result)
        check("clean.tests_found", "tests/" in result["tests_found"], result)
        check("clean.no_warnings", result["warnings"] == [], result)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 2. Repo with unpinned deps and a missing declared dep
# ---------------------------------------------------------------------------

def test_unpinned_and_missing_deps() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        write(tmp / "requirements.txt", "numpy\n")
        write(tmp / "main.py", "import numpy\nimport pandas\nimport requests\n")

        out = tmp / "smoke.json"
        exit_code = run_smoke(tmp, out)
        check("unpinned.exit_code", exit_code == 0, exit_code)

        with open(out) as f:
            result = json.load(f)

        check("unpinned.unpinned_numpy", "numpy" in result["unpinned"], result)
        check(
            "unpinned.missing_pandas_and_requests",
            set(result["missing_declared_deps"]) == {"pandas", "requests"},
            result,
        )
        check("unpinned.entry_point_main", "main.py" in result["entry_points"], result)
        check(
            "unpinned.warnings_present",
            any("README" in w for w in result["warnings"]) and any("tests" in w for w in result["warnings"]),
            result,
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 3. Broken repo: a .py file with a syntax error -- must not crash the
#    whole audit, just warn about that one file.
# ---------------------------------------------------------------------------

def test_broken_repo_with_syntax_error() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        write(tmp / "good.py", "import os\n")
        write(tmp / "broken.py", "def f(:\n    this is not valid python\n")

        out = tmp / "smoke.json"
        exit_code = run_smoke(tmp, out)
        check("broken.exit_code_still_zero", exit_code == 0, exit_code)

        with open(out) as f:
            result = json.load(f)

        check(
            "broken.warning_mentions_broken_file",
            any("broken.py" in w for w in result["warnings"]),
            result,
        )
        check("broken.project_type_still_python", result["project_type"] == "python", result)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_nonexistent_repo_fails_cleanly() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        out = tmp / "smoke.json"
        exit_code = run_smoke(tmp / "does_not_exist", out)
        check("nonexistent.nonzero_exit", exit_code != 0, exit_code)
        check("nonexistent.no_output_written", not out.exists(), "a smoke result should not be written on failure")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 4. Install mode on a tiny local package with no external deps
# ---------------------------------------------------------------------------

def test_install_mode_tiny_local_package() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        write(tmp / "tinypkg" / "__init__.py", "def add(a, b):\n    return a + b\n")
        write(
            tmp / "tests" / "test_tinypkg.py",
            "import sys, os\n"
            "sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))\n"
            "from tinypkg import add\n\n"
            "def test_add():\n"
            "    assert add(1, 2) == 3\n",
        )

        out = tmp / "smoke.json"
        exit_code = run_smoke(tmp, out, ["--install", "--timeout-s", "120"])
        check("install.exit_code", exit_code == 0, exit_code)

        with open(out) as f:
            result = json.load(f)

        check("install.mode", result["mode"] == "install", result)
        check("install.install_ok", result["install_ok"] is True, result)
        check("install.import_ok", result["import_ok"] is True, result)
        check("install.tests_passed", result["tests_passed"] == 1, result)
        check("install.tests_failed", result["tests_failed"] == 0, result)
        check("install.no_errors", result["errors"] == [], result)
        check("install.elapsed_recorded", result["elapsed_s"] > 0, result)

        venv_dir = tmp / ".smoke_venv"
        check("install.venv_confined_to_repo", venv_dir.exists(), "expected the venv inside the repo's own directory")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_example_result_file_is_valid_json() -> None:
    example_path = Path(__file__).resolve().parent.parent.parent / "shared" / "examples" / "worker" / "repo_smoke_result.json"
    if not example_path.exists():
        check("example.exists", False, f"missing {example_path}")
        return
    with open(example_path) as f:
        data = json.load(f)
    check("example.is_object", isinstance(data, dict), data)


def main() -> None:
    tests = [
        test_clean_repo,
        test_unpinned_and_missing_deps,
        test_broken_repo_with_syntax_error,
        test_nonexistent_repo_fails_cleanly,
        test_install_mode_tiny_local_package,
        test_example_result_file_is_valid_json,
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
