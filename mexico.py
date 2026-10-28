"""Mexico: Banxico indicators and the Mexican companies that trade in New York.

BMV prices are not in any free data plan, so the stock side uses the ADRs of
large Mexican companies listed on the NYSE (same company, priced in dollars).
"""
from __future__ import annotations

import datetime as dt

import streamlit as st

import sources as src

# ADRs of Mexican companies listed in New York.
UNIVERSE = {
    "AMX": ("América Móvil", "Telecom"),
    "FMX": ("FEMSA", "Retail & beverages"),
    "KOF": ("Coca-Cola FEMSA", "Beverages"),
    "CX": ("Cemex", "Building materials"),
    "ASR": ("Grupo Aeroportuario del Sureste", "Airports"),
    "PAC": ("Grupo Aeroportuario del Pacífico", "Airports"),
    "OMAB": ("Grupo Aeroportuario Centro Norte", "Airports"),
    "TV": ("Grupo Televisa", "Media & cable"),
}
FALLBACK_TOP5 = ["ASR", "PAC", "FMX", "AMX", "CX"]

# Banxico SIE series. The app also shows Banxico's own title for each one.
SERIES = {
    "fix": "SF43718",        # USD/MXN FIX exchange rate
    "target": "SF61745",     # Banxico target for the overnight interbank rate
    "tiie28": "SF43783",     # TIIE 28 days
    "cetes28": "SF43936",    # CETES 28 days, primary auction yield
    "inflation": "SP30578",  # INPC headline inflation, annual % change
}
INFLATION_TARGET = 3.0  # Banxico's goal, with a +/-1 point band


def indicators() -> dict:
    return src.banxico_latest(tuple(SERIES.values()))


def fix_history(days: int = 400):
    end = dt.date.today()
    return src.banxico_series(SERIES["fix"], (end - dt.timedelta(days=days)).isoformat(), end.isoformat())


def series_history(key: str, years: int = 3):
    end = dt.date.today()
    start = end.replace(year=end.year - years)
    return src.banxico_series(SERIES[key], start.isoformat(), end.isoformat())


def leaderboard() -> list[dict]:
    """Every ADR in the universe ranked by year-to-date return.
    Current price from Finnhub; base = last close of last year from Twelve Data (cached a month)."""
    year = dt.date.today().year
    syms = tuple(UNIVERSE)
    bases = src.year_end_closes(syms, year - 1)
    rows = []
    for s in syms:
        q = src.try_quote(s)
        base = bases.get(s)
        ytd = (q["price"] / base - 1) if q and base else None
        rows.append({"symbol": s, "name": UNIVERSE[s][0], "sector": UNIVERSE[s][1],
                     "price": q["price"] if q else None, "pct": q["pct"] if q else None,
                     "time": q["time"] if q else None, "ytd": ytd})
    rows.sort(key=lambda r: (r["ytd"] is None, -(r["ytd"] or 0)))
    return rows


@st.cache_data(ttl=3 * 3600, show_spinner=False)
def _top5() -> list[str]:
    rows = [r for r in leaderboard() if r["ytd"] is not None]
    if len(rows) < 5:
        raise src.DataError("Not enough YTD data to rank the Mexican ADRs.")
    return [r["symbol"] for r in rows[:5]]


def top5() -> tuple[list[str], bool]:
    """(tickers, live). Falls back to a fixed list, without caching the failure."""
    try:
        return _top5(), True
    except Exception:
        return list(FALLBACK_TOP5), False
