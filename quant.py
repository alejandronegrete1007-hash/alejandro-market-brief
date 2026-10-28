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


# --------------------------------------------------------------------------- growth
def cagr(series: pd.Series, years: int = 5) -> float | None:
    s = series.dropna()
    s = s[s > 0].iloc[-(years + 1):]
    if len(s) < 3:
        return None
    n = (s.index[-1] - s.index[0]).days / 365.25 if isinstance(s.index, pd.DatetimeIndex) else s.index[-1] - s.index[0]
    if n <= 0:
        return None
    return float((s.iloc[-1] / s.iloc[0]) ** (1 / n) - 1)
