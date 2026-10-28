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


# --------------------------------------------------------------------------- relative performance
WINDOWS = {"YTD": None, "6M": 183, "1Y": 365, "2Y": 730}


def window_start(last: pd.Timestamp, window: str) -> pd.Timestamp:
    if window == "YTD":
        return pd.Timestamp(year=last.year, month=1, day=1) - pd.Timedelta(days=1)
    return last - pd.Timedelta(days=WINDOWS[window])


def aligned(series: dict[str, pd.Series]) -> pd.DataFrame:
    """Daily closes on common dates, forward-filled across small holiday gaps."""
    df = pd.concat({k: v for k, v in series.items() if v is not None and len(v)}, axis=1).sort_index()
    return df.ffill(limit=3).dropna()


def rebased(df: pd.DataFrame, start: pd.Timestamp) -> pd.DataFrame:
    """Every column starts at 100 on the last close on or before `start`."""
    base = df[df.index <= start]
    d = df[df.index >= (base.index[-1] if len(base) else df.index[0])]
    return d / d.iloc[0] * 100


def window_return(s: pd.Series, start: pd.Timestamp) -> float | None:
    s = s.dropna()
    base = s[s.index <= start]
    if base.empty:
        return None
    return float(s.iloc[-1] / base.iloc[-1] - 1)


def weekly(df: pd.DataFrame, years: int = 2) -> pd.DataFrame:
    d = df[df.index >= df.index[-1] - pd.DateOffset(years=years)]
    return d.resample("W-FRI").last().pct_change().dropna()


def correlation(stock: pd.Series, bench: pd.Series, years: int = 2) -> float | None:
    w = weekly(pd.concat({"s": stock, "b": bench}, axis=1).dropna(), years)
    return float(w["s"].corr(w["b"])) if len(w) >= 26 else None


def alpha(stock: pd.Series, bench: pd.Series, rf: float, years: int = 1) -> float | None:
    """Jensen's alpha, annualized: return above what beta alone explains."""
    df = pd.concat({"s": stock, "b": bench}, axis=1).dropna()
    df = df[df.index >= df.index[-1] - pd.DateOffset(years=years)]
    r = df.pct_change().dropna()
    if len(r) < 60 or r["b"].var() == 0:
        return None
    rfd = (1 + rf) ** (1 / 252) - 1
    b = r["s"].cov(r["b"]) / r["b"].var()
    return float(((r["s"] - rfd) - b * (r["b"] - rfd)).mean() * 252)


def capture(stock: pd.Series, bench: pd.Series, years: int = 2) -> tuple[float | None, float | None]:
    """Up / down capture on weekly returns: how much of the market's up and down weeks the stock catches."""
    w = weekly(pd.concat({"s": stock, "b": bench}, axis=1).dropna(), years)
    up, dn = w[w["b"] > 0], w[w["b"] < 0]
    uc = float(up["s"].mean() / up["b"].mean()) if len(up) >= 10 else None
    dc = float(dn["s"].mean() / dn["b"].mean()) if len(dn) >= 10 else None
    return uc, dc


def decompose(stock_ret: float, sector_ret: float, market_ret: float) -> dict:
    """Split a return into market + sector-over-market + stock-over-sector (additive, in return points)."""
    return {"market": market_ret, "sector": sector_ret - market_ret, "stock": stock_ret - sector_ret}


# --------------------------------------------------------------------------- outlook
def simulate(close: pd.Series, horizon: int = 126, n: int = 4000, window: int = 504,
             annual_drift: float = 0.0, seed: int = 7) -> np.ndarray:
    """Bootstrap simulation: each future day replays a randomly chosen real daily move from the
    last `window` sessions, re-centred so the average yearly drift equals `annual_drift`.
    Keeps the fat tails real stocks have. Returns price paths shaped (n, horizon)."""
    r = np.log(close.dropna()).diff().dropna().iloc[-window:].to_numpy()
    if len(r) < 60:
        raise ValueError("Not enough history to simulate.")
    r = r - r.mean() + np.log(1 + annual_drift) / TRADING_DAYS
    rng = np.random.default_rng(seed)
    draws = rng.choice(r, size=(n, horizon), replace=True)
    return float(close.dropna().iloc[-1]) * np.exp(np.cumsum(draws, axis=1))


def fan(paths: np.ndarray, qs=(5, 25, 50, 75, 95)) -> pd.DataFrame:
    """Percentile price for each future day (rows) and percentile (columns)."""
    return pd.DataFrame(np.percentile(paths, qs, axis=0).T, columns=list(qs))


def prob_end_above(paths: np.ndarray, level: float, day: int) -> float:
    return float((paths[:, day - 1] > level).mean())


def prob_touch(paths: np.ndarray, level: float, above: bool = True) -> float:
    """Share of paths that reach `level` at any point (high above, or low below)."""
    hit = (paths >= level).any(axis=1) if above else (paths <= level).any(axis=1)
    return float(hit.mean())
