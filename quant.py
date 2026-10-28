"""Pure finance math: returns, risk, statistical ranges and the DCF.

Nothing in here touches the network or Streamlit, so every function can be
unit-tested with synthetic prices (see tests/test_quant.py).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS = 252


# --------------------------------------------------------------------------- returns
def ytd_return(close: pd.Series, year: int | None = None) -> float | None:
    """Return since the last close of the previous calendar year."""
    s = close.dropna()
    if s.empty:
        return None
    year = year or s.index[-1].year
    base = s[s.index < pd.Timestamp(year=year, month=1, day=1)]
    if base.empty:
        return None
    return float(s.iloc[-1] / base.iloc[-1] - 1)


def ytd_from_base(price: float | None, base_close: float | None) -> float | None:
    if not price or not base_close:
        return None
    return price / base_close - 1


def period_return(close: pd.Series, days: int) -> float | None:
    """Return over the last `days` calendar days."""
    s = close.dropna()
    if s.empty:
        return None
    start = s.index[-1] - pd.Timedelta(days=days)
    base = s[s.index <= start]
    if base.empty:
        return None
    return float(s.iloc[-1] / base.iloc[-1] - 1)


# --------------------------------------------------------------------------- risk
def annual_volatility(close: pd.Series, window: int = TRADING_DAYS) -> float | None:
    r = np.log(close.dropna()).diff().dropna().iloc[-window:]
    if len(r) < 20:
        return None
    return float(r.std(ddof=1) * math.sqrt(TRADING_DAYS))


def max_drawdown(close: pd.Series, window: int = TRADING_DAYS) -> float | None:
    s = close.dropna().iloc[-window:]
    if len(s) < 2:
        return None
    dd = s / s.cummax() - 1
    return float(dd.min())


def drawdown_series(close: pd.Series) -> pd.Series:
    s = close.dropna()
    return s / s.cummax() - 1


def beta(stock: pd.Series, bench: pd.Series, years: int = 2) -> float | None:
    """Beta from weekly (Friday) returns over the last `years` years."""
    df = pd.concat({"s": stock, "b": bench}, axis=1).dropna()
    if df.empty:
        return None
    df = df[df.index >= df.index[-1] - pd.DateOffset(years=years)]
    w = df.resample("W-FRI").last().pct_change().dropna()
    if len(w) < 26 or w["b"].var() == 0:
        return None
    return float(w["s"].cov(w["b"]) / w["b"].var())


def sharpe(close: pd.Series, rf: float, window: int = TRADING_DAYS) -> float | None:
    s = close.dropna().iloc[-(window + 1):]
    vol = annual_volatility(s, window)
    if vol is None or vol == 0 or len(s) < 2:
        return None
    total = s.iloc[-1] / s.iloc[0] - 1
    years = (s.index[-1] - s.index[0]).days / 365.25
    if years <= 0:
        return None
    ann = (1 + total) ** (1 / years) - 1
    return float((ann - rf) / vol)


def sma(close: pd.Series, n: int) -> pd.Series:
    return close.rolling(n).mean()


def trend_label(close: pd.Series) -> str:
    """Plain description of where the price sits against its 50- and 200-day averages."""
    s = close.dropna()
    if len(s) < 200:
        return "Not enough history for a 200-day trend"
    p, m50, m200 = s.iloc[-1], sma(s, 50).iloc[-1], sma(s, 200).iloc[-1]
    if p > m50 > m200:
        return "Uptrend: price above the 50-day, which is above the 200-day"
    if p < m50 < m200:
        return "Downtrend: price below the 50-day, which is below the 200-day"
    if p > m200:
        return "Mixed, but still above the 200-day average"
    return "Mixed, and below the 200-day average"


@dataclass
class StatRange:
    horizon_days: int
    low68: float
    high68: float
    low95: float
    high95: float


def statistical_range(price: float, vol: float, horizon_days: int) -> StatRange:
    """Zero-drift lognormal band: where the price lands about 68% / 95% of the time
    if the next months are as volatile as the last year. Not a forecast."""
    s = vol * math.sqrt(horizon_days / TRADING_DAYS)
    return StatRange(
        horizon_days,
        price * math.exp(-s), price * math.exp(s),
        price * math.exp(-1.96 * s), price * math.exp(1.96 * s),
    )


# --------------------------------------------------------------------------- DCF
def cost_of_equity(rf: float, beta_: float | None, erp: float = 0.05) -> float:
    """CAPM, with beta clipped to a sane band so one odd year can't break the model."""
    b = 1.0 if beta_ is None else min(max(beta_, 0.6), 2.0)
    return rf + b * erp


def growth_path(g: float, tg: float, high_years: int = 5, fade_years: int = 5) -> list[float]:
    """`high_years` at g, then a straight-line fade down to the terminal rate."""
    path = [g] * high_years
    for i in range(1, fade_years + 1):
        path.append(g + (tg - g) * i / (fade_years + 1))
    return path


def dcf(fcf0: float, g: float, wacc: float, tg: float, net_debt: float, shares: float,
        high_years: int = 5, fade_years: int = 5) -> dict:
    """Two-stage unlevered DCF on free cash flow. Returns value per share and the pieces."""
    if wacc <= tg:
        raise ValueError("The discount rate must be above the terminal growth rate.")
    if shares <= 0:
        raise ValueError("Shares outstanding must be positive.")
    path = growth_path(g, tg, high_years, fade_years)
    fcf, pv, flows = fcf0, 0.0, []
    for t, gt in enumerate(path, start=1):
        fcf *= 1 + gt
        disc = fcf / (1 + wacc) ** t
        flows.append({"year": t, "growth": gt, "fcf": fcf, "pv": disc})
        pv += disc
    n = len(path)
    tv = fcf * (1 + tg) / (wacc - tg)
    pv_tv = tv / (1 + wacc) ** n
    ev = pv + pv_tv
    equity = ev - net_debt
    return {
        "flows": flows, "pv_fcf": pv, "terminal_value": tv, "pv_terminal": pv_tv,
        "ev": ev, "equity": equity, "per_share": equity / shares,
        "terminal_share": pv_tv / ev if ev else None,
    }


def implied_growth(price: float, fcf0: float, wacc: float, tg: float, net_debt: float,
                   shares: float, lo: float = -0.5, hi: float = 1.5) -> float | None:
    """Reverse DCF: the 5-year growth rate the market price is paying for."""
    if fcf0 <= 0 or wacc <= tg:
        return None
    f = lambda g: dcf(fcf0, g, wacc, tg, net_debt, shares)["per_share"] - price  # noqa: E731
    flo, fhi = f(lo), f(hi)
    if flo > 0 or fhi < 0:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        if f(mid) > 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def sensitivity(fcf0: float, g: float, net_debt: float, shares: float,
                waccs: list[float], tgs: list[float]) -> pd.DataFrame:
    rows = {}
    for w in waccs:
        rows[w] = {t: (dcf(fcf0, g, w, t, net_debt, shares)["per_share"] if w > t else np.nan) for t in tgs}
    return pd.DataFrame(rows).T  # index = WACC, columns = terminal growth


def verdict(value: float, price: float, band: float = 0.10) -> tuple[str, float]:
    """'Undervalued' / 'Fairly valued' / 'Overvalued' with the margin vs price."""
    gap = value / price - 1
    if gap > band:
        return "Undervalued", gap
    if gap < -band:
        return "Overvalued", gap
    return "Fairly valued", gap


def cagr(series: pd.Series, years: int = 5) -> float | None:
    s = series.dropna()
    s = s[s > 0].iloc[-(years + 1):]
    if len(s) < 3:
        return None
    n = (s.index[-1] - s.index[0]).days / 365.25 if isinstance(s.index, pd.DatetimeIndex) else s.index[-1] - s.index[0]
    if n <= 0:
        return None
    return float((s.iloc[-1] / s.iloc[0]) ** (1 / n) - 1)
