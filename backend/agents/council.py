"""Performance Council aggregation and reward (AGENTS.md sections 5 and 5a, D-040).

Three judges, one per model tier, score every finished agent task. This module
combines their scores into Q and blends Q into the outcome term of the reward:

    O = 0.5 * O_det + 0.5 * Q            (O = O_det if the council is unavailable)
    R = 0.6 * O + 0.2 * (1 - C) + 0.2 * F

Pure functions only; the runtime calls the judges and stores the results.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from statistics import mean, median

COUNCIL_WEIGHT = 0.5          # share of O that comes from the council
SPLIT_THRESHOLD = 0.4         # max - min above this marks the council as split
MIN_JUDGES = 2                # fewer valid judges than this => council unavailable


@dataclass(frozen=True)
class CouncilResult:
    q: float | None               # aggregated council score, None if unavailable
    judges: int                   # number of valid judge outputs used
    disagreement: float | None    # max - min of judge overall scores
    split: bool                   # disagreement above SPLIT_THRESHOLD
    failure_pattern: str | None   # label shared by at least 2 judges


def aggregate(judge_outputs: list[dict]) -> CouncilResult:
    """Combine schema-valid judge outputs (shared/schemas/council_judge.json).

    3 judges -> median; 2 judges -> mean; fewer -> unavailable.
    """
    scores = [float(j["overall"]) for j in judge_outputs]
    if len(scores) < MIN_JUDGES:
        return CouncilResult(None, len(scores), None, False, None)

    q = median(scores) if len(scores) >= 3 else mean(scores)
    disagreement = max(scores) - min(scores)

    labels = [
        j["failure_pattern"].strip().lower()
        for j in judge_outputs
        if j.get("failure_pattern")
    ]
    pattern = None
    if labels:
        label, count = Counter(labels).most_common(1)[0]
        if count >= 2:
            pattern = label

    return CouncilResult(
        q=round(q, 4),
        judges=len(scores),
        disagreement=round(disagreement, 4),
        split=disagreement > SPLIT_THRESHOLD,
        failure_pattern=pattern,
    )


def blended_outcome(o_det: float, council: CouncilResult) -> float:
    """O = 0.5 * O_det + 0.5 * Q, or O_det alone when the council is unavailable."""
    if council.q is None:
        return o_det
    return (1 - COUNCIL_WEIGHT) * o_det + COUNCIL_WEIGHT * council.q


def cost(tokens_used: int, token_budget: int, wall_s: float, wall_budget_s: float) -> float:
    """C = 0.5 * min(tokens/budget, 1) + 0.5 * min(wall/budget, 1)."""
    t = min(tokens_used / token_budget, 1.0) if token_budget > 0 else 1.0
    w = min(wall_s / wall_budget_s, 1.0) if wall_budget_s > 0 else 1.0
    return 0.5 * t + 0.5 * w


def feedback_value(feedback: str | None) -> float:
    """Thumbs down = 0, none = 0.5, thumbs up = 1."""
    return {"down": 0.0, "up": 1.0}.get(feedback or "", 0.5)


def reward(o: float, c: float, f: float) -> float:
    """R = 0.6 * O + 0.2 * (1 - C) + 0.2 * F, in [0, 1]."""
    return round(0.6 * o + 0.2 * (1 - c) + 0.2 * f, 4)
