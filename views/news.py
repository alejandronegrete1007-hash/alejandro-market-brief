"""News: every headline the app reads, by market, by sector and for the stocks you hold or follow,
with a one-line AI read of each sector."""
from __future__ import annotations

import datetime as dt
import re

import streamlit as st

import ai
import sources as src
import state
import theme as T
from views.common import click, route

# (name, sector ETF, keywords in English and Spanish; matched at the start of a word)
SECTORS = [
    ("Tech & AI", "XLK", ["ai", "artificial intelligence", "software", "cloud", "apple", "microsoft", "alphabet", "google",
                          "meta", "openai", "anthropic", "oracle", "servicenow", "salesforce", "tech", "inteligencia artificial",
                          "tecnolog", "data center"]),
    ("Semiconductors", "SMH", ["chip", "semiconductor", "nvidia", "amd", "intel", "micron", "tsmc", "broadcom", "qualcomm",
                               "memory", "sandisk", "asml", "hynix", "samsung", "semiconductores"]),
    ("Energy", "XLE", ["oil", "crude", "opec", "natural gas", "exxon", "chevron", "refin", "petróleo", "petroleo", "pemex",
                       "gasolina", "energy", "energía", "brent", "wti", "lng"]),
    ("Banks & finance", "XLF", ["bank", "jpmorgan", "goldman", "morgan stanley", "citigroup", "wells fargo", "fed", "federal reserve",
                                "rate", "treasur", "yield", "bond", "credit", "lend", "banco", "tasa", "banxico", "insur", "private equity"]),
    ("Health care", "XLV", ["pharma", "drug", "fda", "biotech", "vaccine", "health", "medical", "eli lilly", "pfizer", "moderna",
                            "novo nordisk", "unitedhealth", "hospital", "salud", "farmac", "medicare", "obesity", "glp"]),
    ("Consumer & retail", "XLY", ["retail", "walmart", "costco", "target", "consumer", "restaurant", "mcdonald", "chipotle",
                                  "wendy", "starbucks", "nike", "shopper", "amazon", "consumo", "tiendas", "instacart", "doordash"]),
    ("Industrials & autos", "XLI", ["boeing", "airline", "aircraft", "defense", "auto", "ford", "general motors", "tesla",
                                    "stellantis", "railroad", "manufactur", "tariff", "industrial", "aranceles", "automotri",
                                    "transport", "logistic", "fedex", "caterpillar", "nearshoring"]),
    ("Real estate", "XLRE", ["real estate", "housing", "home sales", "mortgage", "reit", "homebuilder", "vivienda", "inmobili"]),
    ("Materials & mining", "XLB", ["gold", "copper", "steel", "aluminum", "lithium", "mining", "metals", "cemex", "oro", "cobre",
                                   "minería", "mineria", "acero", "silver", "plata"]),
    ("Media & telecom", "XLC", ["netflix", "disney", "media", "streaming", "telecom", "verizon", "at&t", "t-mobile", "comcast",
                                "warner", "paramount", "televisa", "américa móvil", "america movil", "telecomunic"]),
    ("Crypto", "IBIT", ["bitcoin", "crypto", "ethereum", "stablecoin", "coinbase", "blockchain", "cripto"]),
]
WHOLE = {"rate", "auto"}  # would also catch "rating", "automation"


def _kw(k: str) -> str:
    """Keywords match at the start of a word ('chip' finds 'chipmaker'); short ones only as a whole word,
    with an optional plural ('ai' must not find 'airline', 'rate' must not find 'rating')."""
    return re.escape(k) + (r"s?(?![a-z0-9])" if len(k) <= 3 or k in WHOLE else "")


_RX = {name: re.compile(r"(?<![a-z0-9])(" + "|".join(_kw(k) for k in kws) + ")", re.I) for name, _, kws in SECTORS}
TONE = {"Positive": "up", "Negative": "down", "Mixed": "flat"}


def _tag(items: list[dict]) -> dict[str, list[dict]]:
    out = {name: [] for name, _, _ in SECTORS}
    for it in items:
        text = f"{it['title']} {it.get('summary', '')}"
        for name, _, _ in SECTORS:
            if _RX[name].search(text):
                out[name].append(it)
    return out


@st.cache_data(ttl=600, show_spinner=False)
def _pool() -> dict:
    """Every headline once, tagged by sector. Cached, because removing near-duplicates among a few hundred
    headlines takes a second or more and doesn't need to run on every click."""
    src.prefetch([(src.recent_headlines, "US"), (src.recent_headlines, "MX"), (src.sector_headlines,)])
    us, f1 = src.recent_headlines("US")
    mx, f2 = src.recent_headlines("MX")
    sec, f3 = src.sector_headlines()
    pool = src.dedupe(us + mx + sec)
    return {"us": us, "mx": mx, "pool": pool, "wall": src.dedupe(us + sec), "tagged": _tag(pool), "failed": f1 + f2 + f3}


def _company_news(symbols: list[str]) -> list[dict]:
    src.prefetch([(src.company_news, s, 4) for s in symbols])
    items = []
    for s in symbols:
        try:
            for n in src.company_news(s, days=4)[:6]:
                items.append({**n, "ticker": s})
        except Exception:
            continue
    return src.dedupe(items)


def _list(items: list[dict], limit: int = 30, tickers: bool = False) -> str:
    if not items:
        return '<div class="amb-empty">No headlines here right now.</div>'
    rows = []
    for n in items[:limit]:
        when = n["time"].strftime("%a %b %d, %H:%M") if n.get("time") else ""
        tk = (f'<span class="amb-tk"{T.go_attr("t:" + n["ticker"])}>{T.esc(n["ticker"])}</span> ' if tickers and n.get("ticker") else "")
        summ = f'<div class="s">{T.esc(n["summary"][:220])}</div>' if n.get("summary") else ""
        rows.append(f'<div class="amb-nrow">{tk}<a href="{T.esc(n["url"])}" target="_blank" rel="noopener">{T.esc(n["title"])}</a>'
                    f'{summ}<div class="m">{T.esc(n["source"])} · {when} ET</div></div>')
    return '<div class="amb-nlist">' + "".join(rows) + "</div>"


def render():
    T.show('<div class="amb-hero"><div><h1>News</h1><div class="sub">Headlines from CNBC, MarketWatch, WSJ, the Fed, '
           'El Financiero, Google News and Finnhub, by market and by sector, plus the news on the stocks you hold and follow.'
           '</div></div></div>')
    with st.spinner("Reading the news feeds..."):
        src.prefetch([(_pool,)] + [(src.try_quote, etf) for _, etf, _ in SECTORS])
        d = _pool()
    us, mx, pool, wall, tagged, failed = d["us"], d["mx"], d["pool"], d["wall"], d["tagged"], d["failed"]

    # ---- sectors: drawn first without the AI read, so the page doesn't wait for Gemini
    blocks = "\n\n".join(f"## {name}\n" + "\n".join(f"- {n['title']}" for n in tagged[name][:12])
                         for name, _, _ in SECTORS if tagged[name])
    T.section("By sector", "click a sector to filter the headlines · AI read of its headlines")
    cards_slot = st.empty()
    with cards_slot.container():
        T.show(_cards(tagged, None, bool(blocks)))
    T.show('<div class="amb-note"><span class="amb-tag ai">AI</span>The tone and the line are written by Gemini only from each '
           'sector\'s headlines; the % is the sector ETF today. Headlines are assigned to sectors by keywords (English and '
           'Spanish), so one can appear in several.</div>')

    # ---- headlines
    sector = st.session_state.get("news_sector")
    T.section("Headlines" + (f" · {sector}" if sector else ""), "newest first · last 36 hours")
    if sector:
        if st.button(f"Show all sectors (now: {sector})", key="news_clear"):
            st.session_state["news_sector"] = None
            st.rerun()
        T.show(_list(tagged[sector], 40))
    else:
        mine = list(dict.fromkeys([p["sym"] for p in (st.session_state.get("pf") or {}).get("positions", [])]
                                  + state.my_list() + state.US_LEADERS))[:10]
        view = st.segmented_control("Show", ["All", "Wall Street", "México", "My stocks"], default="All",
                                    key="news_view", label_visibility="collapsed")
        if view == "Wall Street":
            T.show(_list(wall, 40))
        elif view == "México":
            T.show(_list(mx, 40))
        elif view == "My stocks":
            with st.spinner("Loading company news..."):
                items = _company_news(mine)
            st.caption("Your positions, My stocks and the 2026 leaders: " + ", ".join(mine))
            click(_list(items, 40, tickers=True), "news_mine")
        else:
            T.show(_list(pool, 40))
    if failed:
        T.show(f'<div class="amb-note">Feeds that didn\'t answer this time: {T.esc(", ".join(failed))}</div>')
    try:
        reads = ai.sector_reads(ai.stamp_6h(dt.datetime.now(src.MX)), blocks) if blocks else {}
    except Exception:
        reads = ai.LAST.get("sectors") or {}  # the last good read, else each card shows its newest headline
    with cards_slot.container():
        hit = T.clickable(_cards(tagged, reads, False), "news_sectors")
    if hit and hit.startswith("s:"):
        st.session_state["news_sector"] = None if st.session_state.get("news_sector") == hit[2:] else hit[2:]
        st.rerun()
    elif hit:
        route(hit)
    T.footer("Headlines link to the original articles · refreshed every hour")


def _cards(tagged: dict, reads: dict | None, waiting: bool) -> str:
    """Sector cards. reads=None draws them before the AI read arrives."""
    cards = []
    for name, etf, _ in SECTORS:
        n = len(tagged[name])
        r = (reads or {}).get(name) or {}
        tone = r.get("tone") if r.get("tone") in TONE else None
        q = src.try_quote(etf)
        sel = " sel" if st.session_state.get("news_sector") == name else ""
        tone_html = f'<span class="amb-pill {TONE[tone]}">{tone}</span>' if tone else ""
        count = f"{n} headline" + ("s" if n != 1 else "")
        if not n:
            line = "No headlines in the last 36 hours."
        elif r:
            line = T.esc(r.get("read", ""))
        elif waiting:
            line = '<span style="color:var(--muted)">AI read on its way…</span>'
        else:  # no AI read: the newest headline of the sector instead
            line = f'<span style="color:var(--muted)">Latest:</span> {T.esc(tagged[name][0]["title"])}'
        pct = T.pill(q["pct"]) if q else ""
        cards.append(
            f'<div class="amb-sector{sel}"{T.go_attr("s:" + name)}><div class="top"><span class="nm">{T.esc(name)}</span>{pct}</div>'
            f'<div class="meta">{tone_html}<span>{count} · {etf}</span></div><p>{line}</p></div>')
    return '<div class="amb-grid g3 stack">' + "".join(cards) + "</div>"
