import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import portfolio as P  # noqa: E402


def _returns(n=4, t=150, seed=3):
    rng = np.random.default_rng(seed)
    f = rng.normal(0, 0.02, t)
    data = {f"S{i}": 0.6 * f + rng.normal(0, 0.01 + 0.01 * i, t) for i in range(n)}
    return pd.DataFrame(data)


def test_ledoit_wolf_matches_sklearn():
    sk = pytest.importorskip("sklearn.covariance")
    r = _returns()
    cov, delta = P.ledoit_wolf(r)
    lw = sk.LedoitWolf().fit(r.to_numpy())
    assert delta == pytest.approx(lw.shrinkage_, rel=1e-6)
    assert np.allclose(cov, lw.covariance_)


def test_optimizer_respects_constraints_and_beats_equal_weight():
    r = _returns()
    cov, _ = P.ledoit_wolf(r)
    cov = cov * P.PERIODS
    mu = P.capm_returns({"S0": 0.8, "S1": 1.0, "S2": 1.2, "S3": 1.5}, rf=0.045, erp=0.05)
    w = P.optimize(mu, cov, 0.045, cap=0.4)
    assert w.sum() == pytest.approx(1)
    assert (w >= -1e-9).all() and (w <= 0.4 + 1e-6).all()
    eq = np.full(4, 0.25)
    sh = lambda x: (x @ mu.to_numpy() - 0.045) / np.sqrt(x @ cov @ x)  # noqa: E731
    assert sh(w) >= sh(eq) - 1e-9
    wmin = P.optimize(mu, cov, 0.045, cap=0.4, goal="minvar")
    assert wmin @ cov @ wmin <= eq @ cov @ eq + 1e-12


def test_frontier_is_increasing_in_risk():
    r = _returns()
    cov, _ = P.ledoit_wolf(r)
    mu = P.capm_returns({"S0": 0.8, "S1": 1.0, "S2": 1.2, "S3": 1.5}, rf=0.045, erp=0.05)
    fr = P.frontier(mu, cov * P.PERIODS, 0.045, cap=0.5, points=8)
    assert fr["ret"].is_monotonic_increasing
    assert fr["vol"].iloc[-1] >= fr["vol"].iloc[0]


def test_constant_correlation_shrinkage():
    r = _returns(n=5)
    cov, delta = P.ledoit_wolf_cc(r)
    s = np.cov(r.to_numpy(), rowvar=False, ddof=0)
    assert 0 <= delta <= 1
    assert np.allclose(np.diag(cov), np.diag(s))  # each stock keeps its own variance
    assert np.allclose(cov, cov.T)
    assert np.all(np.linalg.eigvalsh(cov) > 0)


def test_constant_correlation_matches_pyportfolioopt():
    rm = pytest.importorskip("pypfopt.risk_models")
    r = _returns(n=5)
    _, delta = P.ledoit_wolf_cc(r)
    ref = rm.CovarianceShrinkage(r, returns_data=True, frequency=1)
    ref.ledoit_wolf(shrinkage_target="constant_correlation")
    # PyPortfolioOpt uses the n-1 sample covariance; the paper (and this app) use 1/T, so allow a small gap.
    assert delta == pytest.approx(ref.delta, abs=0.02)


def test_pnl_rows_by_hand():
    rows = P.pnl_rows([{"sym": "AAA", "shares": 10, "cost": 50.0, "date": "2026-01-02"}],
                      {"AAA": {"price": 60.0, "change": 2.0, "pct": 3.4483}})
    r = rows.iloc[0]
    assert r["value"] == 600 and r["basis"] == 500 and r["unrl"] == 100
    assert r["daily"] == pytest.approx(20)
    assert r["unrl_pct"] == pytest.approx(0.2)


def test_time_weighted_return_ignores_new_money():
    idx = pd.bdate_range("2026-01-01", periods=4)
    closes = pd.DataFrame({"A": [100, 110, 110, 121], "B": [50, 50, 50, 50]}, index=idx)
    # buy A on day 1; buy B on day 3 (a deposit that must not count as return)
    twr = P.time_weighted([{"sym": "A", "shares": 1, "date": str(idx[0].date())},
                           {"sym": "B", "shares": 10, "date": str(idx[2].date())}], closes)
    # day 2: +10%; day 3: flat; day 4: A +10% on a portfolio of 110 + 500 -> +11/610
    assert twr.iloc[1] == pytest.approx(0.10)
    assert twr.iloc[2] == pytest.approx(0.10)
    assert twr.iloc[3] == pytest.approx(1.10 * (1 + 11 / 610) - 1)


def test_two_stocks_draw_the_full_curve():
    r = _returns(n=2)
    cov, _ = P.ledoit_wolf_cc(r)
    mu = P.capm_returns({"S0": 0.8, "S1": 1.4}, rf=0.045, erp=0.05)
    cap = P.effective_cap(0.35, 2)
    assert cap == 1.0  # a 35% cap would force 50/50
    fr = P.frontier(mu, cov * P.PERIODS, 0.045, cap)
    assert fr["ret"].min() == pytest.approx(mu.min(), abs=1e-6)   # 100% in the low-beta stock
    assert fr["ret"].max() == pytest.approx(mu.max(), abs=1e-6)   # 100% in the high-beta stock
    assert fr["efficient"].any() and (fr["vol"].max() > fr["vol"].min())
