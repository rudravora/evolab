"""Paper-specific task stub. Copy this file into a real experiments/papers/<slug>/
directory and fill in run().

The harness (experiments/harness/run.py) imports this module and calls
run(config) with a dict built from config.yaml plus the --task/--method/
--seed/--budget-min CLI flags merged on top under those exact keys.

run() must return a plain dict of numeric metrics. Optionally include a
"param_count" key (int) -- the harness pulls it out into the result's
param_count field and does not treat it as a plotted metric.

Do not import or require any paper-specific library at module level if that
library might not be installed in every environment running the harness --
import it inside run() instead, so experiments/harness/test_harness.py and
other papers' runs aren't broken by a missing dependency.
"""
from __future__ import annotations


def run(config: dict) -> dict:
    """config always contains at least: task, method, seed, budget_min,
    plus anything from this paper's config.yaml.

    Return a dict of numeric metrics, e.g. {"test_mse": 0.01, "param_count": 128}.
    Raise a normal exception on failure -- the harness catches it, records
    error_signature, and writes a status: "failed" result; don't try to
    catch-and-swallow errors here.
    """
    raise NotImplementedError("fill in run() for this paper")
