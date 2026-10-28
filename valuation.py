"""Five-year DCF, valued four ways: unlevered (FCFF at WACC) and levered (FCFE at
cost of equity), each closed with a perpetual-growth or an EV/EBITDA exit terminal value.

The model is driven by revenue: growth -> revenue, EBITDA margin -> EBITDA,
D&A and capex as % of revenue, net working capital as % of each year's new revenue,
and taxes on EBIT. Pure Python/pandas so every number can be unit-tested.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Inputs:
    revenue0: float          # last fiscal year revenue
    growth: float            # revenue (and earnings) growth, years 1-5
    margin0: float           # EBITDA margin today
    margin_target: float     # EBITDA margin reached in year 5 (linear path)
    da_pct: float            # D&A, % of revenue
    capex_pct: float         # capex, % of revenue
    nwc_pct: float           # NWC investment, % of each year's revenue increase
    tax: float               # tax rate on EBIT
    wacc: float              # discount rate for the unlevered DCF
    ke: float                # cost of equity, discount rate for the levered DCF
    kd: float                # pre-tax cost of debt
    tg: float                # perpetual growth rate
    exit_mult: float         # EV/EBITDA exit multiple
    debt0: float
    cash0: float
    shares: float
    years: int = 5


def wacc(ke: float, kd: float, tax: float, equity: float, debt: float) -> float:
    total = equity + debt
    if total <= 0:
        return ke
    return equity / total * ke + debt / total * kd * (1 - tax)


def adjusted_beta(raw: float | None) -> float:
    """Blume adjustment (what Bloomberg shows as 'adjusted beta'): betas drift toward 1 over time,
    so 2/3 of the measured beta plus 1/3 of the market's."""
    if raw is None:
        return 1.0
    return 0.67 * float(raw) + 0.33


def capm(rf: float, beta: float | None, erp: float = 0.05) -> float:
    """Cost of equity = risk-free rate + beta x equity risk premium."""
    b = 1.0 if beta is None else float(np.clip(beta, 0.5, 2.5))
    return rf + b * erp


def project(a: Inputs) -> pd.DataFrame:
    rows, rev_prev, debt_prev = [], a.revenue0, a.debt0
    for t in range(1, a.years + 1):
        rev = rev_prev * (1 + a.growth)
        margin = a.margin0 + (a.margin_target - a.margin0) * t / a.years
        ebitda = rev * margin
        da = rev * a.da_pct
        ebit = ebitda - da
        taxes = max(ebit, 0) * a.tax
        capex = rev * a.capex_pct
        dnwc = (rev - rev_prev) * a.nwc_pct
        fcff = ebit - taxes + da - capex - dnwc
        debt = debt_prev * (1 + a.growth)            # debt grows with the business
        interest = debt_prev * a.kd
        net_borrow = debt - debt_prev
        fcfe = fcff - interest * (1 - a.tax) + net_borrow
        rows.append({"year": t, "revenue": rev, "margin": margin, "ebitda": ebitda, "da": da, "ebit": ebit,
                     "taxes": taxes, "capex": capex, "dnwc": dnwc, "fcff": fcff, "debt": debt,
                     "interest": interest, "net_borrow": net_borrow, "fcfe": fcfe})
        rev_prev, debt_prev = rev, debt
    return pd.DataFrame(rows).set_index("year")


def terminal_year(a: Inputs, last: pd.Series, tg: float | None = None) -> dict:
    """Year 6, normalized: everything grows at the perpetual rate, so working capital and new
    borrowing reflect steady-state growth instead of the faster growth of years 1-5."""
    tg = a.tg if tg is None else tg
    rev = last["revenue"] * (1 + tg)
    ebitda = rev * a.margin_target
    da = rev * a.da_pct
    ebit = ebitda - da
    fcff = ebit - max(ebit, 0) * a.tax + da - rev * a.capex_pct - (rev - last["revenue"]) * a.nwc_pct
    fcfe = fcff - last["debt"] * a.kd * (1 - a.tax) + last["debt"] * tg
    return {"revenue": rev, "ebitda": ebitda, "fcff": fcff, "fcfe": fcfe}


def value(a: Inputs) -> dict:
    """All four valuations plus the cross-checks bankers look at."""
    if a.wacc <= a.tg or a.ke <= a.tg:
        raise ValueError("Discount rates must be above the perpetual growth rate.")
    if a.shares <= 0:
        raise ValueError("Shares outstanding must be positive.")
    df = project(a)
    n = a.years
    t = np.arange(1, n + 1)
    dw, de = (1 + a.wacc) ** -t, (1 + a.ke) ** -t
    last = df.iloc[-1]

    term = terminal_year(a, last)
    pv_fcff = float((df["fcff"].values * dw).sum())
    tv_u_perp = term["fcff"] / (a.wacc - a.tg)
    tv_u_exit = last["ebitda"] * a.exit_mult
    ev_perp = pv_fcff + tv_u_perp * dw[-1]
    ev_exit = pv_fcff + tv_u_exit * dw[-1]
    net_debt = a.debt0 - a.cash0

    pv_fcfe = float((df["fcfe"].values * de).sum())
    tv_l_perp = term["fcfe"] / (a.ke - a.tg)
    tv_l_exit = last["ebitda"] * a.exit_mult - last["debt"]   # equity at exit
    eq_l_perp = pv_fcfe + tv_l_perp * de[-1] + a.cash0
    eq_l_exit = pv_fcfe + tv_l_exit * de[-1] + a.cash0

    def ps(x):
        return x / a.shares

    out = {
        "projection": df,
        "unlevered": {
            "perpetuity": {"ev": ev_perp, "equity": ev_perp - net_debt, "per_share": ps(ev_perp - net_debt),
                           "tv_share": tv_u_perp * dw[-1] / ev_perp if ev_perp else None},
            "exit": {"ev": ev_exit, "equity": ev_exit - net_debt, "per_share": ps(ev_exit - net_debt),
                     "tv_share": tv_u_exit * dw[-1] / ev_exit if ev_exit else None},
        },
        "levered": {
            "perpetuity": {"equity": eq_l_perp, "per_share": ps(eq_l_perp)},
            "exit": {"equity": eq_l_exit, "per_share": ps(eq_l_exit)},
        },
        # Cross-checks: the multiple the perpetuity method implies, and the growth the exit multiple implies.
        "implied_exit_mult": tv_u_perp / last["ebitda"] if last["ebitda"] > 0 else None,
        "implied_tg": _implied_tg(a, last, tv_u_exit),
        "pv_fcff": pv_fcff, "pv_fcfe": pv_fcfe, "terminal": term,
    }
    vals = [out["unlevered"]["perpetuity"]["per_share"], out["unlevered"]["exit"]["per_share"],
            out["levered"]["perpetuity"]["per_share"], out["levered"]["exit"]["per_share"]]
    out["average"] = float(np.mean(vals))
    out["low"], out["high"] = float(min(vals)), float(max(vals))
    return out


def _implied_tg(a: Inputs, last: pd.Series, tv: float) -> float | None:
    """Perpetual growth that makes the perpetuity terminal value equal the exit-multiple one."""
    def f(g):
        return terminal_year(a, last, g)["fcff"] / (a.wacc - g) - tv
    lo, hi = -0.05, a.wacc - 1e-4
    try:
        flo, fhi = f(lo), f(hi)
    except ZeroDivisionError:
        return None
    if flo > 0 or fhi < 0:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        if f(mid) > 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


SCENARIOS = ("Bear", "Base", "Bull")


def scenario_inputs(a: Inputs, growth_step: float = 0.05, margin_step: float = 0.15,
                    mult_step: float = 0.20, rate_step: float = 0.01) -> dict[str, Inputs]:
    """Bear and bull around the base case: growth ± 5 pts, year-5 margin ± 15% of itself,
    exit multiple ± 20% and discount rates ± 1 pt (higher rates in the bear case)."""
    def shift(k):
        return replace(a, growth=a.growth + k * growth_step,
                       margin_target=a.margin_target * (1 + k * margin_step),
                       exit_mult=max(a.exit_mult * (1 + k * mult_step), 1.0),
                       wacc=a.wacc - k * rate_step, ke=a.ke - k * rate_step)
    return {"Bear": shift(-1), "Base": a, "Bull": shift(1)}


def weighted(values: dict[str, float], probs: dict[str, float]) -> float:
    """Probability-weighted value; probabilities are normalized to sum to one."""
    total = sum(probs.values())
    return sum(values[k] * probs[k] for k in values) / total if total else float("nan")


def implied_growth(a: Inputs, price: float, lo: float = -0.3, hi: float = 1.0) -> float | None:
    """Reverse DCF: the 5-year growth that makes the unlevered perpetuity value equal the price."""
    def f(g):
        return value(replace(a, growth=g))["unlevered"]["perpetuity"]["per_share"] - price
    try:
        flo, fhi = f(lo), f(hi)
    except ValueError:
        return None
    if flo > 0 or fhi < 0:
        return None
    for _ in range(70):
        mid = (lo + hi) / 2
        if f(mid) > 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def grid(a: Inputs, rows: list[float], cols: list[float], col_field: str, pick) -> pd.DataFrame:
    """Sensitivity table: WACC down the rows, `col_field` across the columns."""
    data = {}
    for w in rows:
        r = {}
        for c in cols:
            try:
                r[c] = pick(value(replace(a, wacc=w, **{col_field: c})))
            except ValueError:
                r[c] = np.nan
        data[w] = r
    return pd.DataFrame(data).T


def verdict(intrinsic: float, price: float, band: float = 0.10) -> tuple[str, float]:
    gap = intrinsic / price - 1
    if gap > band:
        return "Undervalued", gap
    if gap < -band:
        return "Overvalued", gap
    return "Fairly valued", gap
