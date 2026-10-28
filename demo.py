"""Synthetic responses for AMB_DEMO=1, shaped like each real API, so the whole app
(including the parsers) can be exercised without keys or network access.
Every number here is fake."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re

import numpy as np
import pandas as pd

LEVEL = {"SPY": 769.7, "QQQ": 721.3, "DIA": 523.3, "IWM": 280.2, "GLD": 372.3, "USO": 163.9, "EWW": 75.0,
         "MRNA": 160.0, "SNDK": 380.0, "DELL": 450.0, "MU": 300.0, "MPC": 520.0,
         "AMX": 24.1, "FMX": 118.0, "KOF": 98.0, "CX": 11.2, "ASR": 345.0, "PAC": 260.0, "OMAB": 108.0, "TV": 3.1}
YTD = {"MRNA": 5.74, "SNDK": 4.29, "DELL": 2.75, "MU": 2.17, "MPC": 1.93, "SPY": 0.16, "QQQ": 0.2, "EWW": 0.22,
       "AMX": 0.31, "FMX": 0.27, "KOF": 0.12, "CX": 0.38, "ASR": 0.18, "PAC": 0.24, "OMAB": 0.09, "TV": -0.21}


def _seed(s: str) -> int:
    return int(hashlib.md5(s.encode()).hexdigest()[:8], 16)


def _path(sym: str, n: int = 520) -> pd.Series:
    rng = np.random.default_rng(_seed(sym))
    days = pd.bdate_range(end=pd.Timestamp.today().normalize() - pd.Timedelta(days=1), periods=n)
    end = LEVEL.get(sym, 50 + _seed(sym) % 300)
    ytd = YTD.get(sym, (_seed(sym) % 60 - 20) / 100)
    year_start = pd.Timestamp(days[-1].year, 1, 1)
    k = int((days < year_start).sum())
    vol = 0.018 if sym in ("SPY", "DIA") else 0.03
    noise = rng.normal(0, vol, n)
    drift_pre = np.full(k, 0.0004)
    drift_post = np.full(n - k, math.log(1 + ytd) / max(n - k, 1))
    r = np.concatenate([drift_pre, drift_post]) + noise
    r -= np.concatenate([np.full(k, noise[:k].mean()), np.full(n - k, noise[k:].mean())])
    p = np.exp(np.cumsum(r))
    p = p / p[-1] * end
    return pd.Series(p, index=days)


def _ts_values(sym: str, start: str | None = None, end: str | None = None, size: int = 520) -> list[dict]:
    s = _path(sym)
    if start:
        s = s[(s.index >= start) & (s.index <= end)]
    else:
        s = s.iloc[-size:]
    rng = np.random.default_rng(_seed(sym + "v"))
    return [{"datetime": d.strftime("%Y-%m-%d"), "open": f"{v * 0.995:.4f}", "high": f"{v * 1.01:.4f}",
             "low": f"{v * 0.99:.4f}", "close": f"{v:.4f}", "volume": str(int(rng.integers(2e6, 3e7)))}
            for d, v in s.iloc[::-1].items()]


def _sec_facts(sym: str) -> dict:
    rng = np.random.default_rng(_seed(sym + "sec"))
    base = LEVEL.get(sym, 100) * 1e9 / 40
    years = list(range(2018, 2026))
    rev = [base * 0.6 * (1.08 ** i) * rng.uniform(0.95, 1.05) for i in range(len(years))]
    ocf = [r * 0.24 for r in rev]
    capex = [r * 0.07 for r in rev]
    if sym == "MRNA":
        ocf = [r * (0.5 if 2020 <= y <= 2022 else -0.4) for r, y in zip(rev, years)]

    def rows(vals):
        return [{"start": f"{y - 1}-09-01", "end": f"{y}-08-31", "val": v, "form": "10-K", "filed": f"{y}-10-15",
                 "fp": "FY", "fy": y} for y, v in zip(years, vals)]
    inst = lambda v: [{"end": "2026-08-31", "val": v, "form": "10-Q", "filed": "2026-10-01"}]  # noqa: E731
    return {
        "entityName": sym + " Corp (demo)",
        "facts": {
            "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
                {"end": "2026-09-30", "val": 1.1e9, "accn": "x", "filed": "2026-10-01"}]}}},
            "us-gaap": {
                "Revenues": {"units": {"USD": rows(rev)}},
                "NetIncomeLoss": {"units": {"USD": rows([r * 0.12 for r in rev])}},
                "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": rows(ocf)}},
                "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": rows(capex)}},
                "OperatingIncomeLoss": {"units": {"USD": rows([r * (0.22 if sym != "MRNA" else -0.35) for r in rev])}},
                "DepreciationDepletionAndAmortization": {"units": {"USD": rows([r * 0.06 for r in rev])}},
                "IncomeTaxExpenseBenefit": {"units": {"USD": rows([r * 0.04 for r in rev])}},
                "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": {"units": {"USD": rows([r * 0.2 for r in rev])}},
                "InterestExpense": {"units": {"USD": rows([base * 0.5 * 0.05] * len(rev))}},
                "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": inst(base * 0.3)}},
                "LongTermDebt": {"units": {"USD": inst(base * 0.5)}},
            },
        },
    }


def _bx_rows(sid: str, start: str, end: str) -> list[dict]:
    idx = pd.bdate_range(start, end) if sid in ("SF43718", "SF61745", "SF43783") else (
        pd.date_range(start, end, freq="W-THU") if sid == "SF43936" else pd.date_range(start, end, freq="MS"))
    rng = np.random.default_rng(_seed(sid))
    n = len(idx)
    if sid == "SF43718":
        v = 19.6 + np.cumsum(rng.normal(-0.003, 0.06, n))
        v = v - v[-1] + 18.6841
    elif sid in ("SF61745", "SF43783"):
        v = np.clip(np.round(np.linspace(11.0, 7.0, n) * 4) / 4, 7.0, 11.25) + (0.25 if sid == "SF43783" else 0)
    elif sid == "SF43936":
        v = np.linspace(10.8, 7.1, n) + rng.normal(0, 0.05, n)
    else:
        v = np.clip(4.6 + np.cumsum(rng.normal(-0.02, 0.15, n)), 3.0, 5.5)
        v = v - v[-1] + 3.76
    return [{"fecha": d.strftime("%d/%m/%Y"), "dato": f"{x:.4f}"} for d, x in zip(idx, v)]


DEMO_TICKERS = ["MRNA", "SNDK", "DELL", "MU", "MPC", "NVDA", "AMX", "FMX", "KOF", "CX", "ASR", "PAC", "OMAB", "TV"]

BX_TITLES = {"SF43718": "Tipo de cambio Pesos por dólar E.U.A. Para solventar obligaciones (FIX)",
             "SF61745": "Tasa objetivo", "SF43783": "TIIE a 28 días", "SF43936": "Cetes a 28 días",
             "SP30578": "Inflación anual INPC"}


def fake_json(url: str, p: dict):
    sym = (p.get("symbol") or "").upper()
    now = dt.datetime.now(dt.timezone.utc)
    if "finnhub" in url:
        if url.endswith("/quote"):
            s = _path(sym)
            rng = np.random.default_rng(_seed(sym + now.strftime("%H")))
            c = s.iloc[-1] * (1 + rng.normal(0.002, 0.012))
            return {"c": c, "d": c - s.iloc[-1], "dp": (c / s.iloc[-1] - 1) * 100, "h": c * 1.012, "l": c * 0.985,
                    "o": s.iloc[-1], "pc": s.iloc[-1], "t": int(now.timestamp()) - 120}
        if "market-status" in url:
            return {"isOpen": False, "session": "post-market", "holiday": None}
        if "profile2" in url:
            return {"name": {"MU": "Micron Technology", "MRNA": "Moderna", "SNDK": "Sandisk", "DELL": "Dell Technologies",
                             "MPC": "Marathon Petroleum"}.get(sym, sym + " Inc"),
                    "finnhubIndustry": "Semiconductors" if sym in ("MU", "SNDK") else "Technology",
                    "logo": "", "weburl": "", "marketCapitalization": 120000, "currency": "USD"}
        if "/stock/metric" in url:
            return {"metric": {"peTTM": 24.3, "forwardPE": 17.8, "psTTM": 5.2, "pbQuarterly": 4.1, "evEbitdaTTM": 13.4,
                               "currentEv/freeCashFlowTTM": 31.0, "netProfitMarginTTM": 18.2, "roeTTM": 22.5,
                               "revenueGrowthTTMYoy": 34.1, "52WeekHigh": LEVEL.get(sym, 100) * 1.08,
                               "52WeekLow": LEVEL.get(sym, 100) * 0.4, "beta": 1.3,
                               "yearToDatePriceReturnDaily": YTD.get(sym, 0.1) * 100, "52WeekPriceReturnDaily": YTD.get(sym, 0.1) * 120}}
        if "/stock/recommendation" in url:
            return [{"period": f"2026-{m:02d}-01", "strongBuy": 8 + m % 3, "buy": 14, "hold": 9 - m % 2, "sell": 1, "strongSell": 0,
                     "symbol": sym} for m in range(10, 4, -1)]
        if "/search" in url:
            q = (p.get("q") or "").upper()
            return {"result": [{"symbol": q[:4] or "NVDA", "description": f"{q} CORP", "type": "Common Stock"},
                               {"symbol": "NVDA", "description": "NVIDIA CORP", "type": "Common Stock"}]}
        if "earnings" in url:
            return {"earningsCalendar": [{"date": (dt.date.today() + dt.timedelta(days=8 + _seed(sym) % 40)).isoformat(),
                                          "hour": "amc", "epsEstimate": 2.1}]}
        if "company-news" in url:
            return [{"headline": f"{sym} {t}", "summary": "Demo summary of the article.", "url": f"https://example.com/{sym}/{i}",
                     "source": "Reuters", "datetime": int(now.timestamp()) - i * 7200}
                    for i, t in enumerate(["shares extend rally as analysts lift estimates", "announces capacity expansion",
                                           "faces questions over pricing", "CEO speaks at industry conference"])]
        if url.endswith("/news"):
            return [{"headline": "Treasury yields edge higher ahead of the Fed decision", "summary": "Demo.",
                     "url": "https://example.com/fh1", "source": "Finnhub", "datetime": int(now.timestamp()) - 3600}]
    if "twelvedata" in url:
        if "," in sym:
            return {s: {"meta": {"symbol": s}, "values": _ts_values(s, p["start_date"], p["end_date"]), "status": "ok"}
                    for s in sym.split(",")}
        if p.get("start_date"):
            return {"meta": {"symbol": sym}, "values": _ts_values(sym, p["start_date"], p["end_date"]), "status": "ok"}
        return {"meta": {"symbol": sym}, "values": _ts_values(sym, size=int(p.get("outputsize", 520))), "status": "ok"}
    if "stlouisfed" in url:
        sid = p["series_id"]
        days = pd.bdate_range(end=dt.date.today() - dt.timedelta(days=1), periods=800)
        rng = np.random.default_rng(_seed(sid))
        if sid == "DGS10":
            v = 4.3 + np.cumsum(rng.normal(0, 0.03, len(days)))
            v = v - v[-1] + 5.00
        else:
            v = np.clip(np.round(np.linspace(5.5, 3.75, len(days)) * 4) / 4, 3.75, 5.5)
        return {"observations": [{"date": d.strftime("%Y-%m-%d"), "value": f"{x:.2f}"} for d, x in zip(days[::-1], v[::-1])]}
    if "coingecko" in url:
        return {"bitcoin": {"usd": 80840.0, "usd_24h_change": 1.14, "last_updated_at": int(now.timestamp()) - 60}}
    if "banxico" in url:
        m = re.search(r"/series/([^/]+)/datos(?:/oportuno|/([\d-]+)/([\d-]+))", url)
        ids = m.group(1).split(",")
        if m.group(2):
            start, end = m.group(2), m.group(3)
        else:
            end = dt.date.today().isoformat()
            start = (dt.date.today() - dt.timedelta(days=70)).isoformat()
        series = []
        for sid in ids:
            rows = _bx_rows(sid, start, end)
            series.append({"idSerie": sid, "titulo": BX_TITLES.get(sid, sid), "datos": rows if m.group(2) else rows[-1:]})
        return {"bmx": {"series": series}}
    if "company_tickers" in url:
        return {str(i): {"cik_str": 1000 + i, "ticker": t, "title": t} for i, t in
                enumerate(DEMO_TICKERS)}
    if "companyfacts" in url:
        cik = int(re.search(r"CIK(\d+)", url).group(1)) - 1000
        return _sec_facts(DEMO_TICKERS[cik])
    if "generativelanguage" in url:
        return {"models": [{"name": "models/gemini-3.0-flash", "supportedGenerationMethods": ["generateContent"]},
                           {"name": "models/gemini-3.0-flash-lite", "supportedGenerationMethods": ["generateContent"]}]}
    raise ValueError(f"demo: no fake for {url}")


def fake_bytes(url: str) -> bytes:
    now = dt.datetime.now(dt.timezone.utc)
    mx = "elfinanciero" in url or "google" in url
    titles = (["Peso cierra con ganancia previo a decisión de la Fed", "Banxico ve espacio para un recorte adicional",
               "BMV avanza 0.3%; Orbia y Cemex lideran", "Remesas suben en septiembre por tercer mes",
               "Inflación de la primera quincena de octubre se modera"] if mx else
              ["Stocks close higher as chipmakers rally ahead of Big Tech earnings", "Fed expected to hold rates on Wednesday",
               "Oil slips as Middle East supply fears ease", "Micron hits record on AI memory demand",
               "Treasury yields climb to 5% on sticky inflation"])
    items = "".join(
        f"<item><title>{t}</title><link>https://example.com/{_seed(url) % 999}/{i}</link><description>Demo summary of: {t}.</description>"
        f"<pubDate>{(now - dt.timedelta(hours=i * 2 + 1)).strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate></item>"
        for i, t in enumerate(titles))
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>demo</title>{items}</channel></rss>'.encode()


def fake_ai(prompt: str) -> dict:
    if "daily brief" in prompt:
        return {
            "headline": "Chip rally lifts Wall Street while the peso holds near 18.70 before the Fed",
            "us": "US stocks rose for a second day, led by semiconductors as investors positioned for Big Tech earnings. "
                  "The 10-year Treasury yield held at 5.00%, a level that keeps pressure on richly valued shares.",
            "mexico": "The peso was steady near 18.68 per dollar, still supported by a wide rate gap with the US. "
                      "Mexican stocks (EWW) were roughly flat as traders waited for the Fed and Banxico's next move.",
            "stories": [
                {"market": "US", "title": "Chipmakers drive the market higher", "what": "Semiconductor shares led gains.",
                 "why": "Chips are now the market's main engine, so their earnings set the tone.", "watch": "Big Tech results this week.",
                 "markets": ["US tech stocks", "Semiconductors"],
                 "impact": [{"ticker": "MU", "direction": "up", "why": "memory prices keep rising"},
                            {"ticker": "SMH", "direction": "up", "why": "chip ETF"}, {"ticker": "FAKEX", "direction": "up", "why": "x"}],
                 "sources": [0, 3]},
                {"market": "US", "title": "The Fed is expected to hold", "what": "Markets price no change on Wednesday.",
                 "why": "A hawkish tone would hit stocks already near records.", "watch": "The statement and the press conference.",
                 "sources": [1, 4]},
                {"market": "MX", "title": "Peso firm before the Fed", "what": "The peso closed with a small gain.",
                 "why": "A strong peso lowers imported inflation and gives Banxico room to cut.", "watch": "Banxico's next decision.",
                 "markets": ["Mexican peso", "Mexican stocks"],
                 "impact": [{"ticker": "EWW", "direction": "up", "why": "stronger peso lifts dollar returns"},
                            {"ticker": "FMX", "direction": "mixed", "why": "peso exposure"}],
                 "sources": [5, 6]},
                {"market": "MX", "title": "Mexican inflation cools", "what": "Mid-October inflation eased.",
                 "why": "It keeps rate cuts on the table.", "watch": "Full-month CPI.", "sources": [9]},
                {"market": "GLOBAL", "title": "Oil eases", "what": "Crude slipped as supply fears faded.",
                 "why": "Cheaper oil helps inflation but hurts refiners like MPC.", "watch": "OPEC+ meeting.", "sources": [2]},
                {"market": "MX", "title": "BMV edges up", "what": "The IPC rose 0.3%.", "why": "Shows local stocks holding up.",
                 "watch": "Q3 reports from large issuers.", "sources": [7, 99]},
            ]}
    return {"situation": "Demo: the stock has more than doubled this year on a sharp upturn in its core market.",
            "momentum": "Price sits above both moving averages; volatility is high, so big swings are normal.",
            "valuation": "Multiples are above the market, and the DCF says the price already assumes strong growth.",
            "bull": "Demand stays tight through next year, so margins keep expanding.",
            "base": "Growth slows to the long-run trend and the stock tracks earnings.",
            "bear": "The cycle turns and prices fall, which hits earnings fast.",
            "risks": ["Cyclical pricing", "High expectations", "Customer concentration"],
            "catalysts": ["Next earnings report"], "unknowns": ["Next year's pricing", "Competitors' capacity plans"],
            "lean": "Hold", "conviction": "Medium",
            "lean_why": "Demo: momentum and analyst support are strong, but the DCF says the price already assumes fast growth.",
            "changes_mind": "A guidance raise that keeps margins near the peak.",
            "vs_consensus": "Less bullish than the Buy consensus because valuation looks full.",
            "bottom_line": "A strong story already well reflected in the price; the next report matters."}


if __name__ == "__main__":
    print(json.dumps(fake_json("https://finnhub.io/api/v1/quote", {"symbol": "MU"}), default=str)[:200])
