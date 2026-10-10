"""Paper-agnostic experiment runner.

Usage:
    python -m experiments.harness.run --paper <slug> --task <name> \
        --method <name> --seed N --budget-min M --out results/

Loads experiments/papers/<slug>/task.py, which must expose:
    run(config: dict) -> dict  # a metrics dict, e.g. {"test_mse": 0.01}

`config.yaml` under the paper's directory (if present) supplies the base
config; `--task`, `--method`, `--seed` and `--budget-min` are merged in on
top under those exact keys, so task.py's run() always sees them regardless
of what config.yaml contains.

Writes results/<run_id>.json in the common schema (result_schema.py) and
exits nonzero with a clear one-line error on failure -- including when the
paper module/task.py is missing, task.py has no run(), run() raises, or the
result fails schema validation (a bug in task.py returning a non-dict, etc).
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import sys
import time
import traceback
import uuid
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

from experiments.harness import result_schema
from experiments.harness.determinism import seed_everything

PAPERS_DIR = Path(__file__).resolve().parent.parent / "papers"


class HarnessError(Exception):
    """Raised for any failure the CLI should report as a clear one-line
    error and a nonzero exit code (missing paper, bad task.py, run() error,
    invalid result)."""


def load_paper_config(paper_slug: str) -> dict:
    config_path = PAPERS_DIR / paper_slug / "config.yaml"
    if not config_path.exists():
        return {}
    if yaml is None:
        raise HarnessError("PyYAML is required to read config.yaml but is not installed")
    with open(config_path) as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise HarnessError(f"{config_path} must contain a YAML mapping at the top level")
    return data


def load_task_module(paper_slug: str):
    task_path = PAPERS_DIR / paper_slug / "task.py"
    if not task_path.exists():
        raise HarnessError(f"no such paper or missing task.py: experiments/papers/{paper_slug}/task.py")

    module_name = f"experiments.papers.{paper_slug}.task"
    spec = importlib.util.spec_from_file_location(module_name, task_path)
    if spec is None or spec.loader is None:
        raise HarnessError(f"could not load task module from {task_path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise HarnessError(f"error importing {task_path}: {exc}") from exc

    if not hasattr(module, "run") or not callable(module.run):
        raise HarnessError(f"{task_path} must define run(config) -> dict")
    return module


def software_versions() -> dict:
    versions = {"python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"}
    try:
        import torch

        versions["torch"] = torch.__version__
    except ImportError:
        pass
    try:
        import sklearn

        versions["scikit-learn"] = sklearn.__version__
    except ImportError:
        pass
    try:
        import numpy

        versions["numpy"] = numpy.__version__
    except ImportError:
        pass
    return versions


def error_signature(exc: BaseException) -> str:
    """A short, stable-ish signature for grouping similar failures: the
    exception type plus its message, truncated. Full traceback stays out of
    the result file to keep it small; use stderr for that.
    """
    return f"{type(exc).__name__}: {exc}"[:500]


def run_once(paper_slug: str, task: str, method: str, seed: int, budget_min: float) -> dict:
    config = load_paper_config(paper_slug)
    module = load_task_module(paper_slug)

    config = dict(config)
    config["task"] = task
    config["method"] = method
    config["seed"] = seed
    config["budget_min"] = budget_min

    seed_everything(seed)

    run_id = f"run_{uuid.uuid4().hex[:16]}"
    start = time.perf_counter()
    try:
        metrics = module.run(config)
    except Exception as exc:
        elapsed = time.perf_counter() - start
        return {
            "run_id": run_id,
            "paper_slug": paper_slug,
            "task": task,
            "method": method,
            "config": config,
            "seed": seed,
            "metrics": {},
            "train_seconds": elapsed,
            "software_versions": software_versions(),
            "status": "failed",
            "param_count": None,
            "error_signature": error_signature(exc),
        }
    elapsed = time.perf_counter() - start

    if not isinstance(metrics, dict):
        raise HarnessError(
            f"experiments/papers/{paper_slug}/task.py run() must return a dict, got {type(metrics).__name__}"
        )

    param_count = metrics.pop("param_count", None)
    numeric_metrics = {}
    for k, v in metrics.items():
        if isinstance(v, bool):
            raise HarnessError(f"metric {k!r} must be numeric, got bool")
        if not isinstance(v, (int, float)):
            raise HarnessError(f"metric {k!r} must be numeric, got {type(v).__name__}")
        numeric_metrics[k] = float(v)

    return {
        "run_id": run_id,
        "paper_slug": paper_slug,
        "task": task,
        "method": method,
        "config": config,
        "seed": seed,
        "metrics": numeric_metrics,
        "train_seconds": elapsed,
        "software_versions": software_versions(),
        "status": "done",
        "param_count": param_count,
        "error_signature": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one experiment and write a result JSON")
    parser.add_argument("--paper", required=True, help="paper slug, e.g. 'kan_demo' (loads experiments/papers/<slug>/task.py)")
    parser.add_argument("--task", required=True, help="task name, e.g. 'x_times_y'")
    parser.add_argument("--method", required=True, help="method name, e.g. 'kan' or 'mlp'")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--budget-min", type=float, required=True, dest="budget_min")
    parser.add_argument("--out", required=True, help="output directory for the result JSON")
    args = parser.parse_args(argv)

    try:
        result = run_once(args.paper, args.task, args.method, args.seed, args.budget_min)
        result_schema.validate(result)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except result_schema.ValidationError as exc:
        print(f"error: result failed schema validation: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error: unexpected failure: {exc}", file=sys.stderr)
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{result['run_id']}.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")

    print(out_path)
    return 0 if result["status"] == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
