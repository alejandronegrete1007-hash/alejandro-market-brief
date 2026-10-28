"""Every external data source lives here, each call wrapped in a Streamlit cache
sized to the provider's free plan.

  Finnhub ....... quotes, market status, company profile, key metrics, news, earnings dates, search
  Twelve Data ... daily price history (charts, YTD, volatility, beta) - 8 requests/min, paced below
  FRED .......... US 10-year Treasury yield and the Fed funds target
  Banxico SIE ... USD/MXN FIX, Banxico target rate, CETES, Mexican inflation
  CoinGecko ..... Bitcoin
  SEC EDGAR ..... reported financials (XBRL company facts) for the DCF
  RSS ........... CNBC, MarketWatch, WSJ, Federal Reserve, El Financiero, Google News (Mexico)

Set AMB_DEMO=1 to run the whole app on synthetic data (see demo.py).
"""
from __future__ import annotations

import datetime as dt
import html as _html
import os
import re
import threading
import time
from collections import deque
from difflib import SequenceMatcher
from zoneinfo import ZoneInfo

import feedparser
import numpy as np
import pandas as pd
import requests
import streamlit as st

ET = ZoneInfo("America/New_York")
MX = ZoneInfo("America/Mexico_City")
TIMEOUT = 15
DEMO = os.environ.get("AMB_DEMO") == "1"
UA = "Mozilla/5.0 (Alejandro Market Brief; personal dashboard)"


class DataError(Exception):
    """A source answered without usable data, or a key is missing."""


def secret(name: str, default=None):
    v = os.environ.get(name)
    if v:
        return v.strip()
    try:
        v = st.secrets[name]
        return v.strip() if isinstance(v, str) else v
    except Exception:
        return default


def get_json(url: str, params: dict | None = None, headers: dict | None = None):
    if DEMO:
        import demo
        return demo.fake_json(url, params or {})
    h = {"User-Agent": UA, **(headers or {})}
    r = requests.get(url, params=params, headers=h, timeout=TIMEOUT)
    if r.status_code == 429:
        raise DataError("Rate limit reached for this source. Give it a minute.")
    if r.status_code in (401, 403):
        raise DataError(f"The source rejected the key ({r.status_code}). Check it in Secrets.")
    if r.status_code >= 400:
        body = re.sub(r"\s+", " ", r.text)[:240]
        raise DataError(f"HTTP {r.status_code} from {url.split('/')[2]}: {body}")
    return r.json()


def get_bytes(url: str) -> bytes:
    if DEMO:
        import demo
        return demo.fake_bytes(url)
    r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.content


def _need(name: str) -> str:
    key = secret(name)
    if not key and not DEMO:
        raise DataError(f"{name} is missing from the app secrets.")
    return key or "demo"


# --------------------------------------------------------------------------- Finnhub
FH = "https://finnhub.io/api/v1"


def _fh(path: str, **params):
    params["token"] = _need("FINNHUB_API_KEY")
    return get_json(FH + path, params)


@st.cache_data(ttl=60, show_spinner=False)
def quote(symbol: str) -> dict:
    q = _fh("/quote", symbol=symbol) or {}
    if not q.get("c") or not q.get("t"):
        raise DataError(f"No quote for {symbol}.")
    return {
        "price": float(q["c"]), "change": q.get("d"), "pct": q.get("dp"),
        "high": q.get("h"), "low": q.get("l"), "open": q.get("o"), "prev": q.get("pc"),
        "time": dt.datetime.fromtimestamp(q["t"], tz=ET),
    }


def try_quote(symbol: str) -> dict | None:
    try:
        return quote(symbol)
    except Exception:
        return None


@st.cache_data(ttl=300, show_spinner=False)
def us_market_status() -> dict:
    try:
        s = _fh("/stock/market-status", exchange="US") or {}
        return {"open": bool(s.get("isOpen")), "session": s.get("session") or "", "holiday": s.get("holiday")}
    except Exception:
        now = dt.datetime.now(ET)
        open_ = now.weekday() < 5 and dt.time(9, 30) <= now.time() < dt.time(16, 0)
        return {"open": open_, "session": "regular" if open_ else "closed", "holiday": None}


def bmv_open() -> bool:
    """Regular BMV hours, 8:30-15:00 Mexico City. Holidays are not checked."""
    now = dt.datetime.now(MX)
    return now.weekday() < 5 and dt.time(8, 30) <= now.time() < dt.time(15, 0)


@st.cache_data(ttl=86400, show_spinner=False)
def profile(symbol: str) -> dict:
    try:
        p = _fh("/stock/profile2", symbol=symbol) or {}
    except Exception:
        p = {}
    return {
        "name": p.get("name") or symbol, "industry": p.get("finnhubIndustry") or "",
        "logo": p.get("logo") or "", "web": p.get("weburl") or "", "country": p.get("country") or "",
        "mcap": (p.get("marketCapitalization") or 0) * 1e6, "currency": p.get("currency") or "USD",
    }


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def key_metrics(symbol: str) -> dict:
    """Finnhub 'basic financials': multiples and ratios, available for ADRs too."""
    m = (_fh("/stock/metric", symbol=symbol, metric="all") or {}).get("metric") or {}
    pick = {
        "pe": m.get("peTTM") or m.get("peBasicExclExtraTTM"),
        "fwd_pe": m.get("forwardPE"),
        "ps": m.get("psTTM"),
        "pb": m.get("pbQuarterly") or m.get("pbAnnual"),
        "ev_ebitda": m.get("evEbitdaTTM"),
        "ev_fcf": m.get("currentEv/freeCashFlowTTM"),
        "net_margin": m.get("netProfitMarginTTM"),
        "roe": m.get("roeTTM"),
        "rev_growth": m.get("revenueGrowthTTMYoy"),
        "div_yield": m.get("currentDividendYieldTTM") or m.get("dividendYieldIndicatedAnnual"),
        "hi52": m.get("52WeekHigh"), "lo52": m.get("52WeekLow"),
        "beta": m.get("beta"),
        "ytd": m.get("yearToDatePriceReturnDaily"),     # percent, as of last close
        "r52": m.get("52WeekPriceReturnDaily"),
    }
    return {k: (float(v) if isinstance(v, (int, float)) else None) for k, v in pick.items()}


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def recommendations(symbol: str) -> list[dict]:
    """Wall Street analyst ratings by month (Finnhub, free): strong buy ... strong sell counts."""
    rows = _fh("/stock/recommendation", symbol=symbol) or []
    return sorted(rows, key=lambda r: r.get("period", ""), reverse=True)


ETFS = {
    "SPY": "S&P 500", "QQQ": "Nasdaq 100", "DIA": "Dow Jones", "IWM": "Russell 2000", "GLD": "Gold",
    "USO": "Oil (WTI)", "EWW": "MSCI Mexico", "TLT": "20Y+ Treasuries", "IEF": "7-10Y Treasuries",
    "HYG": "High yield bonds", "LQD": "Corporate bonds", "XLE": "Energy sector", "XLF": "Financials sector",
    "XLK": "Tech sector", "XLV": "Health care sector", "XLY": "Consumer discretionary", "XLP": "Consumer staples",
    "XLI": "Industrials sector", "XLU": "Utilities sector", "XLB": "Materials sector", "XLRE": "Real estate sector",
    "SMH": "Semiconductors", "SOXX": "Semiconductors", "KRE": "Regional banks", "EEM": "Emerging markets",
    "EWZ": "Brazil", "FXI": "China large caps", "VTI": "US total market", "VOO": "S&P 500", "IBIT": "Bitcoin ETF",
    "SLV": "Silver", "UNG": "Natural gas", "ITA": "Aerospace & defense", "JETS": "Airlines",
    "XLC": "Communication services", "XBI": "Biotech", "IYT": "Transportation", "XHB": "Homebuilders",
    "XRT": "Retail", "PEJ": "Leisure & entertainment", "IGV": "Software",
}

# Finnhub industry -> the sector ETF that best represents it (first keyword match wins).
SECTOR_MAP = [
    ("semiconductor", "SMH"), ("software", "IGV"), ("technology", "XLK"), ("communications", "XLK"),
    ("electrical equipment", "XLK"), ("biotechnology", "XBI"), ("life sciences", "XLV"), ("pharmaceutical", "XLV"),
    ("health", "XLV"), ("oil", "XLE"), ("energy", "XLE"), ("gas", "XLE"), ("bank", "KRE"), ("insurance", "XLF"),
    ("financial", "XLF"), ("capital markets", "XLF"), ("real estate", "XLRE"), ("reit", "XLRE"), ("utilities", "XLU"),
    ("airline", "JETS"), ("aerospace", "ITA"), ("defense", "ITA"), ("logistics", "IYT"), ("road", "IYT"),
    ("marine", "IYT"), ("transportation", "IYT"), ("media", "XLC"), ("telecommunication", "XLC"),
    ("entertainment", "XLC"), ("retail", "XRT"), ("hotels", "PEJ"), ("leisure", "PEJ"), ("automobile", "XLY"),
    ("auto components", "XLY"), ("textiles", "XLY"), ("consumer", "XLY"), ("beverages", "XLP"), ("food", "XLP"),
    ("tobacco", "XLP"), ("chemicals", "XLB"), ("metals", "XLB"), ("mining", "XLB"), ("packaging", "XLB"),
    ("construction", "XLI"), ("building", "XLI"), ("machinery", "XLI"), ("industrial", "XLI"), ("commercial services", "XLI"),
    ("professional services", "XLI"), ("trading companies", "XLI"),
]
SECTOR_CHOICES = ["SMH", "IGV", "XLK", "XLC", "XLV", "XBI", "XLE", "XLF", "KRE", "XLY", "XRT", "XLP", "XLI", "ITA",
                  "IYT", "JETS", "XLB", "XLU", "XLRE", "PEJ", "XHB"]


def sector_etf(industry: str) -> str:
    low = (industry or "").lower()
    for word, etf in SECTOR_MAP:
        if word in low:
            return etf
    return "XLK" if not low else "SPY"


@st.cache_data(ttl=7 * 86400, show_spinner=False)
def peers(symbol: str) -> list[str]:
    """Finnhub's list of comparable companies (same sub-industry), US tickers only."""
    raw = _fh("/stock/peers", symbol=symbol) or []
    known = known_tickers()
    out = []
    for t in raw:
        t = str(t).upper()
        if t != symbol.upper() and US_TICKER.match(t) and (not known or t in known) and t not in out:
            out.append(t)
    return out


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def peer_multiples(symbol: str, limit: int = 8) -> dict:
    """Median and quartiles of the peers' trailing multiples (Finnhub peer group).
    Multiples that are negative or above 200x are left out as not meaningful."""
    vals, used = {"pe": [], "ev_ebitda": [], "ps": []}, []
    for t in peers(symbol)[:limit]:
        try:
            km = key_metrics(t)
        except Exception:
            continue
        hit = False
        for k in vals:
            v = km.get(k)
            if v is not None and 0 < v < 200:
                vals[k].append(v)
                hit = True
        if hit:
            used.append(t)
    out = {"tickers": used}
    for k, v in vals.items():
        if len(v) >= 3:
            a = np.array(v)
            out[k] = {"median": float(np.median(a)), "q1": float(np.percentile(a, 25)),
                      "q3": float(np.percentile(a, 75)), "n": len(v)}
    return out


def is_etf(symbol: str) -> bool:
    return symbol.upper() in ETFS


@st.cache_data(ttl=7 * 86400, show_spinner=False)
def known_tickers() -> frozenset:
    """Tickers we trust exist: every SEC registrant (incl. ADRs) plus common ETFs."""
    try:
        base = set(sec_ciks())
    except Exception:
        base = set()
    return frozenset(base | set(ETFS))


US_TICKER = re.compile(r"^[A-Z]{1,5}(\.[A-Z])?$")


# Big foreign companies whose US-traded ticker (ADR or over-the-counter) name search often misses.
FOREIGN_US_TICKERS = {
    "samsung": ("SSNLF", "Samsung Electronics (US OTC)"), "xiaomi": ("XIACY", "Xiaomi (US ADR, OTC)"),
    "tencent": ("TCEHY", "Tencent (US ADR, OTC)"), "byd": ("BYDDY", "BYD (US ADR, OTC)"),
    "nestle": ("NSRGY", "Nestlé (US ADR, OTC)"), "nestlé": ("NSRGY", "Nestlé (US ADR, OTC)"),
    "lvmh": ("LVMUY", "LVMH (US ADR, OTC)"), "siemens": ("SIEGY", "Siemens (US ADR, OTC)"),
    "roche": ("RHHBY", "Roche (US ADR, OTC)"), "nintendo": ("NTDOY", "Nintendo (US ADR, OTC)"),
    "toyota": ("TM", "Toyota (NYSE ADR)"), "sony": ("SONY", "Sony (NYSE ADR)"), "tsmc": ("TSM", "TSMC (NYSE ADR)"),
    "taiwan semiconductor": ("TSM", "TSMC (NYSE ADR)"), "alibaba": ("BABA", "Alibaba (NYSE ADR)"),
    "asml": ("ASML", "ASML (Nasdaq)"), "sap": ("SAP", "SAP (NYSE ADR)"), "novo nordisk": ("NVO", "Novo Nordisk (NYSE ADR)"),
}


@st.cache_data(ttl=86400, show_spinner=False)
def search(query: str) -> list[dict]:
    low = query.lower().strip()
    out, seen = [], set()
    for name, (sym, label) in FOREIGN_US_TICKERS.items():
        if len(low) >= 3 and (low in name or name in low) and sym not in seen:
            seen.add(sym)
            out.append({"symbol": sym, "name": label})
    res = (_fh("/search", q=query) or {}).get("result") or []
    for r in res:
        sym = (r.get("symbol") or "").upper()
        if r.get("type") in ("Common Stock", "ADR", "GDR", "ETP", "NY Reg Shrs") and US_TICKER.match(sym) and sym not in seen:
            seen.add(sym)
            out.append({"symbol": sym, "name": (r.get("description") or "").title()})
    return out[:8]


@st.cache_data(ttl=43200, show_spinner=False)
def next_earnings(symbol: str) -> dict | None:
    today = dt.date.today()
    try:
        d = _fh("/calendar/earnings", symbol=symbol,
                **{"from": today.isoformat(), "to": (today + dt.timedelta(days=120)).isoformat()}) or {}
    except Exception:
        return None
    cal = [c for c in d.get("earningsCalendar") or [] if c.get("date")]
    if not cal:
        return None
    n = min(cal, key=lambda c: c["date"])
    when = {"bmo": "before the open", "amc": "after the close"}.get(n.get("hour") or "", "")
    return {"date": n["date"], "when": when, "eps_est": n.get("epsEstimate")}


def _item(source, title, summary, url, when, market):
    return {"source": source, "title": title, "summary": summary, "url": url, "time": when, "market": market}


@st.cache_data(ttl=3600, show_spinner=False)
def company_news(symbol: str, days: int = 10) -> list[dict]:
    today = dt.date.today()
    raw = _fh("/company-news", symbol=symbol,
              **{"from": (today - dt.timedelta(days=days)).isoformat(), "to": today.isoformat()}) or []
    items = [
        _item(n.get("source") or "Finnhub", clean(n.get("headline")), clean(n.get("summary"))[:420],
              n.get("url"), dt.datetime.fromtimestamp(n["datetime"], tz=ET) if n.get("datetime") else None, "US")
        for n in raw if n.get("headline") and n.get("url")
    ]
    return dedupe(items)[:12]


# --------------------------------------------------------------------------- Twelve Data
TD = "https://api.twelvedata.com"
_td_lock = threading.Lock()
_td_calls: deque = deque()
TD_PER_MIN = 8


def _td_pace(credits: int = 1):
    """Block until the free plan's 8-credits-per-minute window has room."""
    with _td_lock:
        while True:
            now = time.monotonic()
            while _td_calls and now - _td_calls[0] > 61:
                _td_calls.popleft()
            if len(_td_calls) + credits <= TD_PER_MIN:
                for _ in range(credits):
                    _td_calls.append(now)
                return
            time.sleep(max(0.5, 61 - (now - _td_calls[0])))


def _td(path: str, credits: int = 1, **params):
    params["apikey"] = _need("TWELVE_DATA_API_KEY")
    if not DEMO:
        _td_pace(credits)
    d = get_json(TD + path, params)
    if isinstance(d, dict) and d.get("status") == "error":
        if d.get("code") == 429:
            raise DataError("Twelve Data free limit reached (8 per minute). Refresh in a minute.")
        raise DataError(d.get("message") or "Twelve Data error.")
    return d


def _frame(values: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(values)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime").sort_index()
    for c in ("open", "high", "low", "close", "volume"):
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["close"])


@st.cache_data(ttl=6 * 3600, show_spinner=False, max_entries=60)
def history(symbol: str, outputsize: int = 520) -> pd.DataFrame:
    """Daily OHLCV, oldest first. 520 sessions is a bit over two years."""
    d = _td("/time_series", symbol=symbol, interval="1day", outputsize=outputsize)
    if not d.get("values"):
        raise DataError(f"No price history for {symbol}.")
    return _frame(d["values"])


def try_history(symbol: str) -> pd.DataFrame | None:
    try:
        return history(symbol)
    except Exception:
        return None


@st.cache_data(ttl=30 * 86400, show_spinner=False)
def year_end_closes(symbols: tuple[str, ...], year: int) -> dict[str, float]:
    """Last close of `year` for each symbol, in one batched request. Cached a month:
    it is the fixed base for every YTD figure until next January."""
    d = _td("/time_series", credits=len(symbols), symbol=",".join(symbols), interval="1day",
            start_date=f"{year}-12-20", end_date=f"{year + 1}-01-03")
    if len(symbols) == 1:
        d = {symbols[0]: d}
    out = {}
    for sym in symbols:
        block = d.get(sym) or {}
        vals = [v for v in block.get("values") or [] if v["datetime"][:10] <= f"{year}-12-31"]
        if vals:
            out[sym] = float(max(vals, key=lambda v: v["datetime"])["close"])
    return out


# --------------------------------------------------------------------------- FRED
@st.cache_data(ttl=6 * 3600, show_spinner=False)
def fred(series_id: str, limit: int = 800) -> pd.Series:
    d = get_json("https://api.stlouisfed.org/fred/series/observations", {
        "series_id": series_id, "api_key": _need("FRED_API_KEY"), "file_type": "json",
        "sort_order": "desc", "limit": limit,
    })
    obs = {o["date"]: float(o["value"]) for o in d.get("observations", []) if o.get("value") not in (".", "", None)}
    if not obs:
        raise DataError(f"No data for {series_id}.")
    s = pd.Series(obs, dtype=float)
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def risk_free() -> tuple[float, str]:
    try:
        s = fred("DGS10")
        return s.iloc[-1] / 100, f"US 10Y Treasury {s.iloc[-1]:.2f}% (FRED, {s.index[-1]:%b %d})"
    except Exception:
        return 0.043, "10Y Treasury unavailable - using a 4.30% placeholder"


# --------------------------------------------------------------------------- CoinGecko
@st.cache_data(ttl=600, show_spinner=False)
def bitcoin() -> dict:
    d = get_json("https://api.coingecko.com/api/v3/simple/price", {
        "ids": "bitcoin", "vs_currencies": "usd", "include_24hr_change": "true", "include_last_updated_at": "true",
    })["bitcoin"]
    return {"price": float(d["usd"]), "pct": d.get("usd_24h_change"),
            "time": dt.datetime.fromtimestamp(d["last_updated_at"], tz=ET) if d.get("last_updated_at") else None}


# --------------------------------------------------------------------------- Banxico SIE
BX = "https://www.banxico.org.mx/SieAPIRest/service/v1/series"


def _bx_num(v: str | None) -> float | None:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None  # Banxico sends "N/E" when there is no figure


def _bx(path: str):
    return get_json(BX + path, headers={"Bmx-Token": _need("BANXICO_TOKEN"), "Accept": "application/json"})


def _bx_parse_latest(d: dict) -> dict[str, dict]:
    out = {}
    for s in d.get("bmx", {}).get("series", []):
        datos = [x for x in s.get("datos") or [] if _bx_num(x.get("dato")) is not None]
        if datos:
            x = datos[-1]
            out[s["idSerie"]] = {"value": _bx_num(x["dato"]), "date": dt.datetime.strptime(x["fecha"], "%d/%m/%Y").date(),
                                 "title": s.get("titulo", "")}
    return out


@st.cache_data(ttl=3 * 3600, show_spinner=False)
def banxico_latest(ids: tuple[str, ...]) -> dict[str, dict]:
    """Latest observation of each series, with Banxico's own title for it.
    One request for all; if Banxico rejects it, ask series by series and keep what works."""
    try:
        return _bx_parse_latest(_bx(f"/{','.join(ids)}/datos/oportuno"))
    except DataError as first:
        out, errors = {}, []
        for sid in ids:
            try:
                out.update(_bx_parse_latest(_bx(f"/{sid}/datos/oportuno")))
            except Exception as e:
                errors.append(f"{sid}: {e}")
        if not out:
            raise DataError(f"Banxico: {first}") from None
        return out


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def banxico_series(series_id: str, start: str, end: str) -> pd.Series:
    d = _bx(f"/{series_id}/datos/{start}/{end}")
    rows = {}
    for s in d.get("bmx", {}).get("series", []):
        for x in s.get("datos") or []:
            v = _bx_num(x.get("dato"))
            if v is not None:
                rows[dt.datetime.strptime(x["fecha"], "%d/%m/%Y")] = v
    if not rows:
        raise DataError(f"No Banxico data for {series_id}.")
    return pd.Series(rows, dtype=float).sort_index()


# --------------------------------------------------------------------------- RSS
US_FEEDS = {
    "CNBC": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "CNBC Markets": "https://www.cnbc.com/id/20409666/device/rss/rss.html",
    "MarketWatch": "https://feeds.marketwatch.com/marketwatch/topstories",
    "WSJ Markets": "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain",
    "Federal Reserve": "https://www.federalreserve.gov/feeds/press_all.xml",
}
MX_FEEDS = {
    "El Financiero": "https://www.elfinanciero.com.mx/arc/outboundfeeds/rss/category/mercados/?outputType=xml",
    "El Financiero Economía": "https://www.elfinanciero.com.mx/arc/outboundfeeds/rss/category/economia/?outputType=xml",
    "Google News MX": "https://news.google.com/rss/search?q=BMV+OR+Banxico+OR+%22peso+mexicano%22+OR+%22Bolsa+Mexicana%22+when:2d&hl=es-419&gl=MX&ceid=MX:es-419",
}
_TAG = re.compile(r"<[^>]+>")


def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", _html.unescape(_TAG.sub(" ", text or ""))).strip()


def _parse_feed(source: str, url: str, market: str) -> list[dict]:
    parsed = feedparser.parse(get_bytes(url))
    out = []
    for e in parsed.entries[:30]:
        t = e.get("published_parsed") or e.get("updated_parsed")
        when = dt.datetime(*t[:6], tzinfo=dt.timezone.utc).astimezone(ET) if t else None
        title = clean(e.get("title"))
        src = source
        if source.startswith("Google News") and " - " in title:  # "Headline - Outlet"
            title, src = title.rsplit(" - ", 1)
        if title and e.get("link"):
            out.append(_item(src, title, clean(e.get("summary"))[:420], e.get("link"), when, market))
    if not out:
        raise DataError("empty feed")
    return out


@st.cache_data(ttl=1800, show_spinner=False)
def feeds(market: str) -> tuple[list[dict], list[str]]:
    items, failed = [], []
    for source, url in (US_FEEDS if market == "US" else MX_FEEDS).items():
        try:
            items += _parse_feed(source, url, market)
        except Exception:
            failed.append(source)
    if market == "US":
        try:
            for n in _fh("/news", category="general") or []:
                if n.get("headline") and n.get("url"):
                    items.append(_item(n.get("source") or "Finnhub", clean(n["headline"]), clean(n.get("summary"))[:420],
                                       n["url"], dt.datetime.fromtimestamp(n["datetime"], tz=ET) if n.get("datetime") else None, "US"))
        except Exception:
            failed.append("Finnhub")
    return items, failed


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9áéíóúñ ]", "", t.lower())


def dedupe(items: list[dict], threshold: float = 0.78) -> list[dict]:
    """Newest first, dropping near-duplicate headlines."""
    floor = dt.datetime.min.replace(tzinfo=ET)
    kept, norms = [], []
    for it in sorted(items, key=lambda x: x["time"] or floor, reverse=True):
        n = _norm(it["title"])
        if n and not any(SequenceMatcher(None, n, k).ratio() >= threshold for k in norms):
            kept.append(it)
            norms.append(n)
    return kept


def recent_headlines(market: str) -> tuple[list[dict], list[str]]:
    """Headlines from roughly the last trading day (longer on Mondays and weekends)."""
    now = dt.datetime.now(ET)
    hours = 72 if now.weekday() in (0, 5, 6) else 30
    items, failed = feeds(market)
    cutoff = now - dt.timedelta(hours=hours)
    return dedupe([i for i in items if i["time"] and i["time"] >= cutoff]), failed


# --------------------------------------------------------------------------- SEC EDGAR
def _sec_headers() -> dict:
    return {"User-Agent": secret("SEC_USER_AGENT", "Alejandro Market Brief admin@example.com")}


@st.cache_data(ttl=7 * 86400, show_spinner=False)
def sec_ciks() -> dict[str, int]:
    d = get_json("https://www.sec.gov/files/company_tickers.json", headers=_sec_headers())
    return {v["ticker"].upper(): int(v["cik_str"]) for v in d.values()}


@st.cache_data(ttl=86400, show_spinner=False, max_entries=20)
def sec_facts(ticker: str) -> dict:
    cik = sec_ciks().get(ticker.upper().replace(".", "-"))
    if not cik:
        raise DataError(f"{ticker} is not in the SEC's list of companies.")
    return get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json", headers=_sec_headers())
