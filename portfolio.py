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


def ledoit_wolf_cc(returns: pd.DataFrame) -> tuple[np.ndarray, float]:
    """Ledoit-Wolf (2004, 'Honey, I shrunk the sample covariance matrix') shrinkage toward the
    constant-correlation target: every pair gets the average correlation, while each stock keeps its
    own variance. Better suited to stocks than the identity target, and the stocks' volatilities are
    left untouched. Returns the shrunk covariance (per period) and the shrinkage intensity."""
    x = returns.to_numpy(dtype=float)
    t, n = x.shape
    y = x - x.mean(axis=0)
    s = y.T @ y / t
    var = np.diag(s)
    sd = np.sqrt(var)
    corr = s / np.outer(sd, sd)
    rbar = (corr.sum() - n) / (n * (n - 1))
    f = rbar * np.outer(sd, sd)
    np.fill_diagonal(f, var)
    y2 = y ** 2
    pi_mat = (y2.T @ y2) / t - s ** 2
    pi_hat = pi_mat.sum()
    theta_ii = (y ** 3).T @ y / t - var[:, None] * s       # theta_ii,ij  (row i, column j)
    theta_jj = theta_ii.T                                   # theta_jj,ij
    ratio = np.outer(1 / sd, sd)                            # sqrt(s_jj / s_ii) at (i, j)
    rho_off = rbar / 2 * (ratio * theta_ii + ratio.T * theta_jj)
    np.fill_diagonal(rho_off, 0)
    rho_hat = np.trace(pi_mat) + rho_off.sum()
    gamma_hat = ((f - s) ** 2).sum()
    kappa = (pi_hat - rho_hat) / gamma_hat if gamma_hat > 0 else 0.0
    delta = float(max(0.0, min(1.0, kappa / t)))
    return delta * f + (1 - delta) * s, delta


def capm_returns(betas: dict[str, float], rf: float, erp: float) -> pd.Series:
    return pd.Series({k: rf + v * erp for k, v in betas.items()})


def _stats(w, mu, cov):
    ret = float(w @ mu)
    vol = float(np.sqrt(max(w @ cov @ w, 0)))
    return ret, vol


def optimize(mu: pd.Series, cov: np.ndarray, rf: float, cap: float = 0.35, goal: str = "sharpe",
             target: float | None = None) -> np.ndarray:
    """Long-only weights. goal: 'sharpe' (tangency), 'minvar', or 'target' (min variance for a target return).
    The Sharpe ratio is not convex, so the tangency search starts from several points and keeps the best."""
    n = len(mu)
    m = mu.to_numpy()
    cap = max(cap, 1.0 / n)
    if goal == "sharpe":
        best, best_s = None, -np.inf
        starts = [np.full(n, 1 / n)] + [_cap_fill(np.eye(n)[i], cap) for i in range(n)]
        for w0 in starts:
            w = _solve(m, cov, rf, cap, "sharpe", None, w0)
            r, v = _stats(w, m, cov)
            sr = (r - rf) / v if v > 0 else -np.inf
            if sr > best_s:
                best, best_s = w, sr
        return best
    return _solve(m, cov, rf, cap, goal, target, np.full(n, 1 / n))


def _cap_fill(e: np.ndarray, cap: float) -> np.ndarray:
    """A feasible starting point leaning on one asset: as much of it as the cap allows, the rest spread evenly."""
    n = len(e)
    w = e * cap
    rest = 1 - w.sum()
    others = (1 - e) / max(n - 1, 1)
    return w + others * rest


def _solve(m, cov, rf, cap, goal, target, w0) -> np.ndarray:
    n = len(m)
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
    res = minimize(obj, w0, method="SLSQP", bounds=[(0, cap)] * n, constraints=cons,
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


# --------------------------------------------------------------------------- positions and P&L
def pnl_rows(positions: list[dict], quotes: dict[str, dict | None]) -> pd.DataFrame:
    """One row per position, the way a broker shows it: market value, daily and unrealized P&L."""
    rows = []
    for p in positions:
        q = quotes.get(p["sym"])
        last = q["price"] if q else None
        prev = (q["price"] - q["change"]) if q and q.get("change") is not None else None
        sh, cost = p["shares"], p["cost"]
        mv = sh * last if last is not None else None
        rows.append({
            "sym": p["sym"], "shares": sh, "last": last, "chg_pct": (q["pct"] / 100) if q else None,
            "daily": sh * (last - prev) if last is not None and prev is not None else None,
            "avg": cost, "basis": sh * cost, "value": mv,
            "unrl": mv - sh * cost if mv is not None else None,
            "unrl_pct": (last / cost - 1) if last is not None else None, "date": p.get("date") or "",
        })
    return pd.DataFrame(rows)


def time_weighted(positions: list[dict], closes: pd.DataFrame) -> pd.Series:
    """Time-weighted return of the stock holdings since the first purchase, from daily closes.
    Each purchase is new money (an external flow) on its date, so returns are not inflated by deposits:
    r_t = (V_t - F_t) / V_(t-1) - 1, where F_t is the value bought on day t."""
    starts = {}
    for p in positions:
        if p["sym"] not in closes.columns:
            continue
        d = pd.Timestamp(p["date"]) if p.get("date") else closes.index[0]
        d = max(d, closes[p["sym"]].dropna().index[0])
        starts.setdefault(p["sym"], []).append((d, p["shares"]))
    if not starts:
        return pd.Series(dtype=float)
    first = min(d for lst in starts.values() for d, _ in lst)
    df = closes[closes.index >= first].ffill()
    value = pd.Series(0.0, index=df.index)
    flow = pd.Series(0.0, index=df.index)
    for sym, lst in starts.items():
        for d, sh in lst:
            on = df.index >= d
            value[on] += sh * df.loc[on, sym]
            day = df.index[on][0]
            flow[day] += sh * df.loc[day, sym]
    prev = value.shift(1)
    r = ((value - flow) / prev - 1).where(prev > 0, 0.0).fillna(0.0)
    return (1 + r).cumprod() - 1


def holdings_risk(weights: pd.Series, returns: pd.DataFrame, bench: pd.Series, level: float = 0.95) -> dict:
    """Risk of today's weights applied to the last two years of daily returns (historical simulation)."""
    w = weights / weights.sum()
    r = returns[w.index].dropna()
    port = r @ w.values
    b = bench.reindex(port.index).dropna()
    p2 = port.reindex(b.index)
    q = float(np.quantile(port, 1 - level))
    return {"vol": float(port.std(ddof=1) * np.sqrt(252)),
            "var": -q, "cvar": -float(port[port <= q].mean()),
            "beta": float(p2.cov(b) / b.var()) if len(b) > 30 and b.var() > 0 else None,
            "effective_n": float(1 / np.sum(w.values ** 2)), "days": int(len(port))}
