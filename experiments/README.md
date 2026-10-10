# experiments/ environment

CPU-only Python environment for the experiment harness (paper-agnostic). Verified on macOS, Apple Silicon (arm64), system Python 3.14.7.

## Recreate from scratch

Requires [`uv`](https://docs.astral.sh/uv/) (or substitute `python3.14 -m venv .venv` plus `pip install -r requirements.lock`).

```bash
cd experiments
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python -r requirements.lock
```

## Verify the environment

```bash
.venv/bin/python smoke_test.py
```

Should finish in well under 2 minutes and print the installed Python/torch/scikit-learn versions plus test error, parameter count and training time for a tiny torch MLP and a scikit-learn Ridge model on synthetic data.

## Notes

- `.venv/` is gitignored; `requirements.lock` has exact pins (no ranges) and is the source of truth for reproducing the environment.
- CPU-only `torch` wheels and `scikit-learn` wheels both install cleanly on Python 3.14 (arm64) as of this writing — no fallback to an older Python was needed. If a future dependency lacks a 3.14 wheel, recreate the venv with `--python 3.11` or `3.12` instead and re-freeze.
- No paper-specific libraries are pinned here yet — those get added in a separate change under `experiments/papers/<slug>/` once the demo paper is chosen, and `requirements.lock` gets re-frozen (`uv pip freeze --python .venv/bin/python > requirements.lock`) at that point.
