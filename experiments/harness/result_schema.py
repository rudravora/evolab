"""Common result schema for every experiment run, any paper.

A single JSON shape so the backend's Evaluator/Ledger/Reporter (and any
report-generation script in this repo) can read results from any paper
without paper-specific parsing. Paper-specific code never defines its own
result shape -- it returns a plain metrics dict from run(config), and the
harness (experiments/harness/run.py) wraps that into a Result here.

Mirrors ARCHITECTURE.md's experiments table (seed, config_json, metrics_json,
cost_s, status) plus identifying fields (run_id, paper_slug, task, method)
and fields useful for the KAN-vs-MLP-shaped comparisons this project expects
(param_count, software_versions) -- see result_schema.py's REQUIRED_FIELDS
for exactly what validate() checks.
"""
from __future__ import annotations

import dataclasses
from typing import Any

STATUS_VALUES = ("done", "failed")

REQUIRED_FIELDS = (
    "run_id",
    "paper_slug",
    "task",
    "method",
    "config",
    "seed",
    "metrics",
    "train_seconds",
    "software_versions",
    "status",
)


@dataclasses.dataclass
class Result:
    run_id: str
    paper_slug: str
    task: str
    method: str
    config: dict[str, Any]
    seed: int
    metrics: dict[str, float]
    train_seconds: float
    software_versions: dict[str, str]
    status: str  # "done" | "failed"
    param_count: int | None = None
    error_signature: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class ValidationError(Exception):
    pass


def validate(data: dict[str, Any]) -> None:
    """Raise ValidationError with a clear message if `data` does not match
    the common result schema. Does not mutate `data`.
    """
    if not isinstance(data, dict):
        raise ValidationError(f"result must be a JSON object, got {type(data).__name__}")

    missing = [f for f in REQUIRED_FIELDS if f not in data]
    if missing:
        raise ValidationError(f"missing required field(s): {missing}")

    if not isinstance(data["run_id"], str) or not data["run_id"]:
        raise ValidationError("run_id must be a non-empty string")
    if not isinstance(data["paper_slug"], str) or not data["paper_slug"]:
        raise ValidationError("paper_slug must be a non-empty string")
    if not isinstance(data["task"], str) or not data["task"]:
        raise ValidationError("task must be a non-empty string")
    if not isinstance(data["method"], str) or not data["method"]:
        raise ValidationError("method must be a non-empty string")
    if not isinstance(data["config"], dict):
        raise ValidationError("config must be a JSON object")
    if not isinstance(data["seed"], int) or isinstance(data["seed"], bool):
        raise ValidationError("seed must be an integer")
    if not isinstance(data["metrics"], dict):
        raise ValidationError("metrics must be a JSON object")
    for k, v in data["metrics"].items():
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ValidationError(f"metrics[{k!r}] must be a number, got {type(v).__name__}")
    if not isinstance(data["train_seconds"], (int, float)) or isinstance(data["train_seconds"], bool):
        raise ValidationError("train_seconds must be a number")
    if data["train_seconds"] < 0:
        raise ValidationError("train_seconds must be >= 0")
    if not isinstance(data["software_versions"], dict):
        raise ValidationError("software_versions must be a JSON object")
    if data["status"] not in STATUS_VALUES:
        raise ValidationError(f"status must be one of {STATUS_VALUES}, got {data['status']!r}")

    if "param_count" in data and data["param_count"] is not None:
        if not isinstance(data["param_count"], int) or isinstance(data["param_count"], bool):
            raise ValidationError("param_count must be an integer or null")
        if data["param_count"] < 0:
            raise ValidationError("param_count must be >= 0")

    if data["status"] == "failed":
        if not data.get("error_signature"):
            raise ValidationError("status is 'failed' but error_signature is missing or empty")
    if "error_signature" in data and data["error_signature"] is not None:
        if not isinstance(data["error_signature"], str):
            raise ValidationError("error_signature must be a string or null")
