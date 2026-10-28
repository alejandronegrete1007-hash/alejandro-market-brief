"""Mean-variance portfolio construction (Markowitz), as in the seminar's portfolio unit.

Expected returns come from CAPM (risk-free + beta x equity premium) rather than past returns,
which are far too noisy to optimize on. Risk is the covariance of weekly returns, shrunk toward
a constant-variance target with the Ledoit-Wolf (2004) formula so a few volatile weeks don't
dominate. Long-only, fully invested, with a cap on any single stock.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

PERIODS = 52  # weekly returns per year


def ledoit_wolf(returns: pd.DataFrame) -> tuple[np.ndarray, float]:
    """Shrunk covariance and the shrinkage intensity (0 = sample covariance, 1 = target)."""
    x = returns.to_numpy(dtype=float)
    x = x - x.mean(axis=0)
    t, n = x.shape
    s = x.T @ x / t
    mu = np.trace(s) / n
    f = mu * np.eye(n)
    d2 = np.sum((s - f) ** 2) / n
    b2 = sum(np.sum((np.outer(r, r) - s) ** 2) for r in x) / (t ** 2 * n)
    b2 = min(b2, d2)
    delta = b2 / d2 if d2 > 0 else 1.0
    return delta * f + (1 - delta) * s, float(delta)


def capm_returns(betas: dict[str, float], rf: float, erp: float) -> pd.Series:
    return pd.Series({k: rf + v * erp for k, v in betas.items()})


def _stats(w, mu, cov):
    ret = float(w @ mu)
    vol = float(np.sqrt(max(w @ cov @ w, 0)))
    return ret, vol


def optimize(mu: pd.Series, cov: np.ndarray, rf: float, cap: float = 0.35, goal: str = "sharpe",
             target: float | None = None) -> np.ndarray:
    """Long-only weights. goal: 'sharpe' (tangency), 'minvar', or 'target' (min variance for a target return)."""
    n = len(mu)
    m = mu.to_numpy()
    cap = max(cap, 1.0 / n)
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1}]
    if goal == "target":
        cons.append({"type": "eq", "fun": lambda w: w @ m - target})
    if goal == "sharpe":
        def obj(w):
            r, v = _stats(w, m, cov)
            return -(r - rf) / v if v > 0 else 0.0
    else:
        def obj(w):
            return float(w @ cov @ w)
    res = minimize(obj, np.full(n, 1 / n), method="SLSQP", bounds=[(0, cap)] * n, constraints=cons,
                   options={"maxiter": 500, "ftol": 1e-12})
    w = np.clip(res.x, 0, None)
    return w / w.sum()


def frontier(mu: pd.Series, cov: np.ndarray, rf: float, cap: float = 0.35, points: int = 25) -> pd.DataFrame:
    """Efficient frontier from the minimum-variance portfolio to the highest reachable return."""
    m = mu.to_numpy()
    w_min = optimize(mu, cov, rf, cap, "minvar")
    lo = float(w_min @ m)
    # highest return with the cap: fill the best assets up to the cap
    order = np.argsort(-m)
    w_hi, left = np.zeros(len(m)), 1.0
    for i in order:
        take = min(max(cap, 1 / len(m)), left)
        w_hi[i], left = take, left - take
        if left <= 1e-12:
            break
    hi = float(w_hi @ m)
    rows = []
    for tr in np.linspace(lo, hi, points):
        w = optimize(mu, cov, rf, cap, "target", tr) if tr > lo + 1e-9 else w_min
        r, v = _stats(w, m, cov)
        rows.append({"ret": r, "vol": v})
    return pd.DataFrame(rows)


def describe(w: np.ndarray, mu: pd.Series, cov: np.ndarray, rf: float) -> dict:
    r, v = _stats(w, mu.to_numpy(), cov)
    return {"ret": r, "vol": v, "sharpe": (r - rf) / v if v else None,
            "weights": dict(zip(mu.index, w)), "effective_n": float(1 / np.sum(w ** 2))}
