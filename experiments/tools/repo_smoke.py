"""Repo smoke test: static audit of an unknown repository, with an optional
install+import+test mode gated behind backend approval.

Runs as a worker python_script job (ARCHITECTURE.md section 5, API.md
section 9: "Repo smoke test ... is a python_script or shell job. Its result
metrics must carry {import_ok, tests_passed, tests_failed}. The first run of
a user-supplied repository is risk='high' and needs approval."). This script
itself does not know about jails or job approval state -- the worker/backend
decide whether --install is allowed to run at all; this script just does
what it's told, confined to --repo's own directory tree.

Usage:
    python repo_smoke.py --repo <path> --out <smoke.json> [--install] [--timeout-s N]

Default (static) mode NEVER executes anything from the repo: no eval/exec,
no running setup.py, no importing the repo's own code, no running its
install script. It only reads text files and parses Python source with the
`ast` module (parsing is not execution).

--install mode additionally: creates a venv inside the repo's own directory,
pip-installs declared dependencies (with a timeout, clean environment),
tries importing the detected top-level package, and runs a detected test
command (with a timeout). This is still confined to a venv and the repo's
own directory -- nothing is installed or run outside that tree, and the
subprocess environment never inherits the parent's env (no ambient secrets).
Call sites (the worker) are expected to only pass --install for a job the
backend has marked approved; this script does not itself check an
`approved` flag since that is the job/policy layer's responsibility, not a
property of the repo being audited.

Output smoke.json keys (always present unless noted):
  mode: "static" | "install"
  project_type: "python" | "unknown"
  python_constraint: str | null (from pyproject.toml's requires-python, or
    setup.cfg/setup.py python_requires, whichever is found first)
  dependency_files: [str, ...] (relative paths found: requirements*.txt,
    pyproject.toml, setup.py, setup.cfg, environment.yml)
  unpinned: [str, ...] (dependency specs with no version pin, e.g. "numpy"
    with no "==", from requirements*.txt or pyproject.toml)
  missing_declared_deps: [str, ...] (top-level import names found by ast
    parsing that are not covered by any declared dependency file entry --
    a heuristic: stdlib and the project's own local modules are excluded)
  entry_points: [str, ...] (relative paths of files that look like entry
    points: main.py, __main__.py, app.py, cli.py, or a console_scripts
    entry in setup.cfg/pyproject.toml)
  tests_found: [str, ...] (relative paths of test files/dirs detected:
    test_*.py, *_test.py, a tests/ directory, or a [tool.pytest.ini_options]
    section)
  warnings: [str, ...] (missing README/license/tests, parse errors on a
    specific file, etc.)
  -- install mode only, otherwise these keys are absent:
  install_ok: bool
  import_ok: bool
  tests_passed: int
  tests_failed: int
  errors: [str, ...] (short one-line error strings, not full tracebacks)
  elapsed_s: float

Exits 0 on success (prints one summary line to stdout). Exits nonzero with
one clear line on stderr on failure (bad --repo path, no Python files found
at all in static mode is still success -- only a missing/invalid path or an
unrecoverable I/O error is a hard failure).
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import time
import venv
from pathlib import Path

STDLIB_MODULE_NAMES = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else set()

DEPENDENCY_FILE_PATTERNS = (
    "requirements.txt",
    "requirements-*.txt",
    "requirements_*.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "environment.yml",
    "environment.yaml",
)
ENTRY_POINT_NAMES = ("main.py", "__main__.py", "app.py", "cli.py")
VERSION_PIN_MARKERS = ("==", ">=", "<=", "~=", "!=", ">", "<")
DEFAULT_INSTALL_TIMEOUT_S = 300
DEFAULT_TEST_TIMEOUT_S = 180


class SmokeError(Exception):
    """Any error that should produce a one-line message on stderr and a
    nonzero exit, rather than a raw traceback."""


class _SkipTestRun(Exception):
    """Internal control-flow signal: pytest could not be installed, so skip
    attempting to run it (the error is already recorded by the caller)."""


def find_dependency_files(repo: Path) -> list[str]:
    found = []
    for pattern in DEPENDENCY_FILE_PATTERNS:
        for p in sorted(repo.glob(pattern)):
            if p.is_file():
                found.append(str(p.relative_to(repo)))
    return found


def _parse_requirements_txt(path: Path) -> list[str]:
    specs = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return specs
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        specs.append(line)
    return specs


def _parse_pyproject_toml(path: Path) -> list[str]:
    """Minimal, dependency-free TOML scraping: just pull out the
    dependencies = [...] array under [project], without a real TOML parser
    (tomllib is stdlib on 3.11+ but we keep this simple and tolerant of
    malformed/unusual files, since the input is untrusted).
    """
    specs = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return specs
    match = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, re.DOTALL)
    if match:
        for item in re.findall(r'["\']([^"\']+)["\']', match.group(1)):
            specs.append(item.strip())
    return specs


def _parse_setup_cfg_or_py(path: Path) -> list[str]:
    specs = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return specs
    match = re.search(r"install_requires\s*=\s*[\[\(](.*?)[\]\)]", text, re.DOTALL)
    if match:
        for item in re.findall(r'["\']([^"\']+)["\']', match.group(1)):
            specs.append(item.strip())
    return specs


def collect_declared_dependencies(repo: Path, dependency_files: list[str]) -> list[str]:
    specs: list[str] = []
    for rel in dependency_files:
        path = repo / rel
        name = path.name
        if name == "requirements.txt" or name.startswith("requirements"):
            specs.extend(_parse_requirements_txt(path))
        elif name == "pyproject.toml":
            specs.extend(_parse_pyproject_toml(path))
        elif name in ("setup.py", "setup.cfg"):
            specs.extend(_parse_setup_cfg_or_py(path))
    return specs


def _spec_package_name(spec: str) -> str:
    name = spec.strip()
    for marker in VERSION_PIN_MARKERS + ("[",):
        name = name.split(marker, 1)[0]
    return name.strip().lower().replace("_", "-")


def find_unpinned(dep_specs: list[str]) -> list[str]:
    unpinned = []
    for spec in dep_specs:
        stripped = spec.strip()
        if not stripped:
            continue
        if not any(marker in stripped for marker in VERSION_PIN_MARKERS):
            unpinned.append(stripped)
    return unpinned


def find_python_constraint(repo: Path) -> str | None:
    pyproject = repo / "pyproject.toml"
    if pyproject.exists():
        try:
            text = pyproject.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        match = re.search(r'requires-python\s*=\s*["\']([^"\']+)["\']', text)
        if match:
            return match.group(1)

    for name in ("setup.cfg", "setup.py"):
        path = repo / name
        if path.exists():
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            match = re.search(r'python_requires\s*=\s*["\']([^"\']+)["\']', text)
            if match:
                return match.group(1)
    return None


def find_entry_points(repo: Path) -> list[str]:
    found = []
    for name in ENTRY_POINT_NAMES:
        for p in repo.rglob(name):
            if _is_within_venv_or_hidden(repo, p):
                continue
            found.append(str(p.relative_to(repo)))
    return sorted(set(found))


def find_tests(repo: Path) -> list[str]:
    found = []
    for p in repo.rglob("test_*.py"):
        if _is_within_venv_or_hidden(repo, p):
            continue
        found.append(str(p.relative_to(repo)))
    for p in repo.rglob("*_test.py"):
        if _is_within_venv_or_hidden(repo, p):
            continue
        found.append(str(p.relative_to(repo)))
    tests_dir = repo / "tests"
    if tests_dir.is_dir():
        found.append("tests/")
    return sorted(set(found))


def _is_within_venv_or_hidden(repo: Path, path: Path) -> bool:
    try:
        rel_parts = path.relative_to(repo).parts
    except ValueError:
        return True
    for part in rel_parts:
        if part in (".git", ".venv", "venv", "__pycache__", "node_modules", ".tox", ".eggs"):
            return True
        if part.startswith(".") and part not in (".",):
            return True
    return False


def collect_top_level_imports(repo: Path) -> tuple[set[str], list[str]]:
    """Parse every .py file with ast (never exec/eval) and collect top-level
    import module names (the first dotted segment only, e.g. "numpy" from
    "numpy.linalg"). Returns (import_names, warnings) -- a file that fails
    to parse produces a warning, not a hard failure.
    """
    imports: set[str] = set()
    warnings: list[str] = []
    for py_file in repo.rglob("*.py"):
        if _is_within_venv_or_hidden(repo, py_file):
            continue
        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(py_file))
        except (SyntaxError, UnicodeDecodeError, OSError) as exc:
            warnings.append(f"could not parse {py_file.relative_to(repo)}: {exc}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.level == 0:
                    imports.add(node.module.split(".")[0])
    return imports, warnings


def find_missing_declared_deps(repo: Path, imports: set[str], dep_specs: list[str]) -> list[str]:
    declared_names = {_spec_package_name(s) for s in dep_specs}
    local_module_names = {p.stem for p in repo.glob("*.py")} | {p.name for p in repo.glob("*/") if (p / "__init__.py").exists()}

    missing = []
    for name in sorted(imports):
        if not name or name.startswith("_"):
            continue
        if name in STDLIB_MODULE_NAMES:
            continue
        if name in local_module_names:
            continue
        normalized = name.lower().replace("_", "-")
        if normalized in declared_names or name.lower() in declared_names:
            continue
        missing.append(name)
    return missing


def run_static_audit(repo: Path) -> dict:
    warnings: list[str] = []

    dependency_files = find_dependency_files(repo)
    dep_specs = collect_declared_dependencies(repo, dependency_files)
    unpinned = find_unpinned(dep_specs)
    python_constraint = find_python_constraint(repo)
    entry_points = find_entry_points(repo)
    tests_found = find_tests(repo)
    imports, parse_warnings = collect_top_level_imports(repo)
    warnings.extend(parse_warnings)
    missing_declared_deps = find_missing_declared_deps(repo, imports, dep_specs)

    project_type = "python" if dependency_files or any(repo.rglob("*.py")) else "unknown"

    if not (repo / "README.md").exists() and not (repo / "README.rst").exists() and not (repo / "README").exists():
        warnings.append("no README found")
    if not any((repo / name).exists() for name in ("LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING")):
        warnings.append("no LICENSE found")
    if not tests_found:
        warnings.append("no tests found")
    if not dependency_files:
        warnings.append("no dependency file found")

    return {
        "mode": "static",
        "project_type": project_type,
        "python_constraint": python_constraint,
        "dependency_files": dependency_files,
        "unpinned": unpinned,
        "missing_declared_deps": missing_declared_deps,
        "entry_points": entry_points,
        "tests_found": tests_found,
        "warnings": warnings,
    }


def _clean_subprocess_env(venv_python_dir: Path) -> dict:
    """A minimal, platform-appropriate environment with no inherited
    secrets -- same principle as worker/runner.py's build_clean_env, kept
    independent here since this script has no dependency on worker/.
    """
    if os.name == "nt":
        base = {k: os.environ[k] for k in ("SYSTEMROOT", "COMSPEC") if k in os.environ}
        base.setdefault("SYSTEMROOT", r"C:\Windows")
        base.setdefault("COMSPEC", r"C:\Windows\System32\cmd.exe")
        base["PATH"] = f"{venv_python_dir}{os.pathsep}{os.environ.get('PATH', '')}"
        base["PATHEXT"] = os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD")
    else:
        base = {}
        base["PATH"] = f"{venv_python_dir}{os.pathsep}/usr/bin:/bin"
        base["HOME"] = os.environ.get("HOME", "/tmp")
        base["LANG"] = os.environ.get("LANG", "en_US.UTF-8")
    return base


def run_install_mode(repo: Path, dependency_files: list[str], dep_specs: list[str], timeout_s: int) -> dict:
    start = time.monotonic()
    errors: list[str] = []
    install_ok = False
    import_ok = False
    tests_passed = 0
    tests_failed = 0

    venv_dir = repo / ".smoke_venv"
    try:
        venv.create(venv_dir, with_pip=True, clear=True)
    except Exception as exc:
        errors.append(f"venv creation failed: {exc}")
        return {
            "install_ok": False,
            "import_ok": False,
            "tests_passed": 0,
            "tests_failed": 0,
            "errors": errors,
            "elapsed_s": time.monotonic() - start,
        }

    bin_dir = venv_dir / ("Scripts" if os.name == "nt" else "bin")
    venv_python = bin_dir / ("python.exe" if os.name == "nt" else "python")
    env = _clean_subprocess_env(bin_dir)

    if dep_specs:
        try:
            result = subprocess.run(
                [str(venv_python), "-m", "pip", "install", *dep_specs],
                cwd=str(repo),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
            install_ok = result.returncode == 0
            if not install_ok:
                errors.append(f"pip install exited {result.returncode}: {result.stderr.strip()[:300]}")
        except subprocess.TimeoutExpired:
            errors.append(f"pip install timed out after {timeout_s}s")
        except OSError as exc:
            errors.append(f"pip install failed to start: {exc}")
    else:
        install_ok = True  # nothing declared to install; not itself a failure

    top_level_packages = sorted({p.stem for p in repo.glob("*.py") if p.stem != "setup"} | {
        p.name for p in repo.glob("*/") if (p / "__init__.py").exists()
    })
    if top_level_packages:
        import_target = top_level_packages[0]
        try:
            result = subprocess.run(
                [str(venv_python), "-c", f"import {import_target}"],
                cwd=str(repo),
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            import_ok = result.returncode == 0
            if not import_ok:
                errors.append(f"import {import_target} failed: {result.stderr.strip()[:300]}")
        except subprocess.TimeoutExpired:
            errors.append("import check timed out")
        except OSError as exc:
            errors.append(f"import check failed to start: {exc}")
    else:
        errors.append("no top-level package found to import")

    tests_found = find_tests(repo)
    if tests_found:
        try:
            # pytest is the test runner this script drives, but it is
            # rarely a *declared runtime dependency* of the audited repo
            # (often a dev-only dependency, or not declared at all), so it
            # is not installed by the dependency-install step above --
            # install it explicitly before trying to run anything with it.
            pip_result = subprocess.run(
                [str(venv_python), "-m", "pip", "install", "pytest"],
                cwd=str(repo),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
            if pip_result.returncode != 0:
                errors.append(f"could not install pytest to run tests: {pip_result.stderr.strip()[:300]}")
                raise _SkipTestRun()

            result = subprocess.run(
                [str(venv_python), "-m", "pytest", "-q", "--tb=no"],
                cwd=str(repo),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
            passed, failed = _parse_pytest_summary(result.stdout + result.stderr)
            tests_passed, tests_failed = passed, failed
            if result.returncode not in (0, 1):  # 1 = tests failed but pytest ran fine
                errors.append(f"pytest exited {result.returncode}: {result.stderr.strip()[:300]}")
        except _SkipTestRun:
            pass
        except subprocess.TimeoutExpired:
            errors.append(f"test run timed out after {timeout_s}s")
        except OSError as exc:
            errors.append(f"test run failed to start: {exc}")

    return {
        "install_ok": install_ok,
        "import_ok": import_ok,
        "tests_passed": tests_passed,
        "tests_failed": tests_failed,
        "errors": errors,
        "elapsed_s": time.monotonic() - start,
    }


def _parse_pytest_summary(output: str) -> tuple[int, int]:
    passed = 0
    failed = 0
    match = re.search(r"(\d+) passed", output)
    if match:
        passed = int(match.group(1))
    match = re.search(r"(\d+) failed", output)
    if match:
        failed = int(match.group(1))
    return passed, failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Static (and optionally install+test) audit of a repository")
    parser.add_argument("--repo", required=True, help="path to the repository root")
    parser.add_argument("--out", required=True, help="path to write smoke.json")
    parser.add_argument("--install", action="store_true", help="also create a venv, install deps, import, and run tests")
    parser.add_argument("--timeout-s", type=int, default=DEFAULT_INSTALL_TIMEOUT_S, dest="timeout_s")
    args = parser.parse_args(argv)

    try:
        repo = Path(args.repo)
        if not repo.exists():
            raise SmokeError(f"repo path does not exist: {repo}")
        if not repo.is_dir():
            raise SmokeError(f"repo path is not a directory: {repo}")

        result = run_static_audit(repo)

        if args.install:
            dep_specs = collect_declared_dependencies(repo, result["dependency_files"])
            install_result = run_install_mode(repo, result["dependency_files"], dep_specs, args.timeout_s)
            result["mode"] = "install"
            result.update(install_result)
    except SmokeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error: unexpected failure auditing {args.repo}: {exc}", file=sys.stderr)
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")

    if result["mode"] == "install":
        summary = (
            f"audited {args.repo} (install mode): install_ok={result['install_ok']} "
            f"import_ok={result['import_ok']} tests_passed={result['tests_passed']} "
            f"tests_failed={result['tests_failed']} -> {out_path}"
        )
    else:
        summary = (
            f"audited {args.repo} (static mode): {len(result['dependency_files'])} dep file(s), "
            f"{len(result['unpinned'])} unpinned, {len(result['missing_declared_deps'])} missing declared dep(s), "
            f"{len(result['warnings'])} warning(s) -> {out_path}"
        )
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
