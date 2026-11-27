import math

import pytest

from dashboard.stats import summarize, wilson_ci


def test_wilson_ci_brackets_the_proportion():
    lo, hi = wilson_ci(35, 100)
    assert lo < 0.35 < hi
    assert lo == pytest.approx(0.2636, abs=1e-3)
    assert hi == pytest.approx(0.4474, abs=1e-3)


def test_wilson_ci_empty():
    assert all(math.isnan(v) for v in wilson_ci(0, 0))


def test_summarize(trades):
    s = summarize(trades)
    assert s.n == 4
    assert s.days == 3
    assert s.win_rate == 0.5
    assert s.total_pnl == pytest.approx(60.0)
    assert s.expectancy == pytest.approx(15.0)
    assert s.profit_factor == pytest.approx(140 / 80)
    assert s.payoff_ratio == pytest.approx(70 / 40)
    lo, hi = s.expectancy_ci
    assert lo <= hi


def test_bootstrap_is_reproducible(trades):
    assert summarize(trades).expectancy_ci == summarize(trades).expectancy_ci
