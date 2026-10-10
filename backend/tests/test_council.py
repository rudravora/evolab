"""Council aggregation and reward blending (AGENTS.md section 5a, D-040)."""

import pytest

from agents.council import aggregate, blended_outcome, cost, feedback_value, reward


def judge(overall, pattern=None):
    return {"overall": overall, "failure_pattern": pattern}


def test_three_judges_use_median():
    r = aggregate([judge(0.2), judge(0.7), judge(0.9)])
    assert r.q == 0.7 and r.judges == 3
    assert r.disagreement == pytest.approx(0.7)
    assert r.split is True


def test_two_judges_use_mean():
    r = aggregate([judge(0.6), judge(0.8)])
    assert r.q == pytest.approx(0.7)
    assert r.split is False


def test_fewer_than_two_judges_is_unavailable_and_falls_back_to_o_det():
    r = aggregate([judge(0.9)])
    assert r.q is None
    assert blended_outcome(0.4, r) == 0.4


def test_blend_is_half_and_half():
    r = aggregate([judge(0.8), judge(0.8), judge(0.8)])
    assert blended_outcome(0.4, r) == pytest.approx(0.6)


def test_failure_pattern_needs_two_matching_judges():
    assert aggregate([judge(0.3, "Wrong pykan API"), judge(0.4, "wrong pykan api "), judge(0.5)]).failure_pattern == "wrong pykan api"
    assert aggregate([judge(0.3, "a"), judge(0.4, "b"), judge(0.5)]).failure_pattern is None


def test_reward_formula():
    c = cost(tokens_used=5000, token_budget=10000, wall_s=30, wall_budget_s=60)
    assert c == pytest.approx(0.5)
    assert feedback_value(None) == 0.5 and feedback_value("up") == 1.0 and feedback_value("down") == 0.0
    # O = 0.5*1.0 + 0.5*0.8 = 0.9 ; R = 0.6*0.9 + 0.2*0.5 + 0.2*0.5 = 0.74
    o = blended_outcome(1.0, aggregate([judge(0.8)] * 3))
    assert reward(o, c, 0.5) == pytest.approx(0.74)


def test_cost_saturates_at_one():
    assert cost(10**9, 10, 10**9, 1) == 1.0
