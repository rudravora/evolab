# Paper template

Copy this directory to `experiments/papers/<slug>/` (a short, filesystem-safe
name — lowercase, underscores) and fill in each file before running anything
through the harness.

- **config.yaml** — base config for this paper's `task.py`. The harness
  overwrites `task`, `method`, `seed` and `budget_min` with the CLI flags on
  every run, so put only paper-specific defaults here (hyperparameters,
  dataset paths, model sizes).
- **axes.yaml** — the what-if axes worth exploring for this paper, and the
  values to try on each. Not read by the harness itself; it's the
  human/Designer-facing list of what varies.
- **paper_claims.yaml** — fill in by hand from the actual paper. One entry
  per claim: the claim text, which metric it's about, the paper's claimed
  value, and where in the paper it came from (page/table/figure). This is
  what later evaluation compares your results against.
- **task.py** — must define `run(config: dict) -> dict`. Gets called once
  per experiment run with a merged config (this paper's config.yaml plus the
  CLI's task/method/seed/budget_min). Returns a flat dict of numeric
  metrics, optionally with a `param_count` key.
- **README.md** — this file; replace with notes specific to the paper once
  you fill the directory in (what the paper claims, where the data comes
  from, anything a teammate would need to pick this up).

Run it with:

```bash
python -m experiments.harness.run --paper <slug> --task <task_name> \
    --method <method_name> --seed 0 --budget-min 5 --out results/
```
