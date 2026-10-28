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
