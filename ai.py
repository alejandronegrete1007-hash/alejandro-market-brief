"""Gemini (free tier) writes the daily brief and the per-stock take.

The model only sees numbers and headlines the app already fetched, and has to
answer in JSON that cites headline numbers, so every story can be traced back
to its sources. Anything it cites that doesn't exist is dropped.
"""
from __future__ import annotations

import hashlib
import json
import re

import requests
import streamlit as st

import sources as src

API = "https://generativelanguage.googleapis.com/v1beta"
PREFERRED = [r"^gemini-[\d.]+-flash$", r"^gemini-flash-latest$", r"^gemini-[\d.]+-flash-lite$",
             r"^gemini-flash-lite-latest$", r"flash"]


class AIError(Exception):
    pass


def _key() -> str:
    k = src.secret("GEMINI_API_KEY")
    if not k and not src.DEMO:
        raise AIError("GEMINI_API_KEY is missing from the app secrets.")
    return k or "demo"


def _version(name: str) -> float:
    m = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
    return float(m.group(1)) if m else 0.0


@st.cache_data(ttl=86400, show_spinner=False)
def models() -> list[str]:
    """Text models this key can use, best first: newest fast 'flash' models, then the rest.
    (Fixed model names get retired and start returning 404, so the app asks Google.)"""
    forced = src.secret("GEMINI_MODEL")
    d = src.get_json(f"{API}/models", {"pageSize": 200}, headers={"x-goog-api-key": _key()})
    names = [m["name"].split("/")[-1] for m in d.get("models", [])
             if "generateContent" in (m.get("supportedGenerationMethods") or [])]
    names = [n for n in names if not any(x in n for x in ("preview", "exp", "tts", "image", "live", "audio"))] or names
    ranked: list[str] = [forced] if forced else []
    for pat in PREFERRED:
        for n in sorted((n for n in names if re.search(pat, n)), key=_version, reverse=True):
            if n not in ranked:
                ranked.append(n)
    ranked += [n for n in names if n not in ranked]
    if not ranked:
        raise AIError("This Gemini key has no text models available.")
    return ranked


def pick_model() -> str:
    return models()[0]


def _thinking(model: str) -> dict:
    """Keep 'thinking' short: a news summary doesn't need long reasoning, and it makes
    the answer arrive in seconds instead of minutes."""
    if _version(model) >= 3:
        return {"thinkingLevel": "low"}
    if "2.5" in model:
        return {"thinkingBudget": 0}
    return {}


def _post(model: str, prompt: str, temperature: float, thinking: dict):
    cfg = {"temperature": temperature, "responseMimeType": "application/json"}
    if thinking:
        cfg["thinkingConfig"] = thinking
    return requests.post(f"{API}/models/{model}:generateContent",
                         json={"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": cfg},
                         headers={"x-goog-api-key": _key()}, timeout=40)


def _read(r) -> dict:
    parts = r.json()["candidates"][0]["content"]["parts"]
    text = [p["text"] for p in parts if p.get("text") and not p.get("thought")][-1]
    return json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip()).strip())


def _generate(prompt: str, temperature: float = 0.3) -> dict:
    if src.DEMO:
        import demo
        return demo.fake_ai(prompt)
    last = "no model tried"
    for model in models()[:4]:  # slow, busy (503), retired (404) or out of quota (429): try the next one
        try:
            r = _post(model, prompt, temperature, _thinking(model))
            if r.status_code == 400 and _thinking(model):  # model doesn't take that setting
                r = _post(model, prompt, temperature, {})
        except requests.RequestException as e:
            last = f"{model}: {'too slow' if isinstance(e, requests.Timeout) else e.__class__.__name__}"
            continue
        if r.status_code in (404, 429, 500, 503):
            last = f"{model} returned {r.status_code}"
            continue
        if r.status_code >= 400:
            raise AIError(f"Gemini returned an error ({r.status_code}).")
        try:
            return _read(r)
        except Exception:
            last = f"{model}: unreadable answer"
    raise AIError(f"Gemini is busy or out of free quota right now ({last}). Try again in a few minutes.")


STYLE = """Write like a sharp buy-side analyst explaining the market to a smart friend:
plain English, precise, no hype, no jargon without a short explanation. Use ONLY the
data and headlines provided. Never invent numbers, events, dates, price targets or
probabilities. If something isn't in the inputs, don't say it."""


@st.cache_data(ttl=6 * 3600, show_spinner=False, max_entries=8)
def daily_brief(snapshot: str, headlines: tuple[str, ...], stamp: str) -> dict:
    """`stamp` (date + 6-hour block) makes the brief refresh four times a day at most."""
    numbered = "\n".join(f"[{i}] {h}" for i, h in enumerate(headlines))
    prompt = f"""{STYLE}

You are writing the daily brief of 'Alejandro Market Brief', which covers two markets:
the United States (Wall Street) and Mexico (BMV, peso, Banxico).

MARKET DATA (already verified):
{snapshot}

HEADLINES (number, market, source, time, title, summary):
{numbered}

Return JSON exactly like:
{{
  "headline": "one line, max 14 words, the single most important thing today",
  "us": "2-3 sentences on Wall Street today, using the market data",
  "mexico": "2-3 sentences on Mexico today: peso, rates, Mexican stocks",
  "stories": [
    {{"market": "US" | "MX" | "GLOBAL", "title": "short, clear title",
      "what": "what happened, 1-2 sentences",
      "why": "why it matters for investors, 1-2 sentences",
      "watch": "what to watch next, 1 sentence",
      "markets": ["2-4 markets or asset classes it moves, e.g. 'US tech stocks', 'Mexican peso', 'Oil', 'US Treasuries'"],
      "impact": [{{"ticker": "US-listed ticker", "direction": "up" | "down" | "mixed", "why": "max 8 words"}}],
      "sources": [headline numbers that support this story]}}
  ]
}}
Pick 6 stories, ranked by market importance, at least 2 about Mexico if the headlines allow.
Merge headlines about the same event into one story and cite all of them.
For "impact" list 1-4 tickers that trade in New York and are directly exposed: the companies named in the
headlines first, then the clearest sector or country ETF (e.g. SMH chips, XLE energy, KRE regional banks, EWW Mexico,
TLT long Treasuries, GLD gold, USO oil). For Mexico use NYSE-listed Mexican ADRs (AMX, FMX, KOF, CX, ASR, PAC, OMAB, TV)
or EWW. "direction" is the likely first reaction implied by the news, not a forecast; use "mixed" when unclear."""
    out = _generate(prompt)
    n = len(headlines)
    stories = []
    for s in out.get("stories") or []:
        ids = [i for i in s.get("sources") or [] if isinstance(i, int) and 0 <= i < n]
        if ids and s.get("title"):
            s["sources"] = ids
            stories.append(s)
    out["stories"] = stories
    return out


@st.cache_data(ttl=24 * 3600, show_spinner=False, max_entries=30)
def research_note(symbol: str, facts: str, news: tuple[str, ...], day: str) -> dict:
    """An equity research note built only from the app's data: thesis, valuation, quality, scenarios, risks."""
    numbered = "\n".join(f"[{i}] {h}" for i, h in enumerate(news)) or "(no recent company news)"
    prompt = f"""{STYLE}

Write a one-page equity research note on {symbol}, the way a buy-side analyst at an asset manager
would present it to the investment committee. Today is {day}.

DATA AND CALCULATIONS FROM THE APP (treat as facts; the DCF uses the analyst's own assumptions):
{facts}

RECENT NEWS:
{numbered}

Return JSON exactly like:
{{
  "one_liner": "the thesis in one sentence, max 30 words",
  "thesis": ["3 numbered-style points, each 1-2 sentences, each tied to a number from the data"],
  "variant": "1-2 sentences: where this view differs from the Wall Street consensus given, or why it agrees",
  "valuation": "2-3 sentences: probability-weighted DCF vs price, what the price implies (reverse DCF), and the peers' multiples",
  "quality": "1-2 sentences on financial health: margins, cash conversion, leverage, ROIC vs WACC / EVA, citing the numbers",
  "bull": "bull case: what has to go right, and the value it points to",
  "base": "base case and its assumption",
  "bear": "bear case: what would go wrong, and the value it points to",
  "catalysts": ["up to 3 upcoming events supported by the inputs (e.g. the earnings date)"],
  "risks": ["3 short risks, most important first"],
  "monitor": ["2-3 metrics to track that would confirm or break the thesis"],
  "lean": "Buy" | "Hold" | "Sell",
  "conviction": "Low" | "Medium" | "High",
  "lean_why": "2-3 sentences: why that lean, weighing valuation, quality, momentum, risk and the consensus",
  "changes_mind": "one sentence: what would flip the lean",
  "bottom_line": "one sentence"
}}
Never invent numbers, events, price targets or dates. The lean is a model opinion for the analyst's own research;
if the data is thin or contradictory, choose "Hold" with "Low" conviction and say why."""
    return _generate(prompt, temperature=0.35)


@st.cache_data(ttl=3 * 3600, show_spinner=False, max_entries=8)
def sector_reads(blocks: str, stamp: str) -> dict:
    """One line and a tone per sector, from that sector's headlines only."""
    prompt = f"""{STYLE}

For each sector below, read ONLY its headlines and return its tone for investors today and one sentence
(max 28 words) on what is driving it. Tone is "Positive", "Negative" or "Mixed"; use "Mixed" when the
headlines conflict or are thin. Do not mention sectors with no headlines.

{blocks}

Return JSON exactly like: {{"sectors": {{"<sector name>": {{"tone": "Positive", "read": "..."}}}}}}"""
    out = _generate(prompt, temperature=0.2)
    return out.get("sectors") or {}


@st.cache_data(ttl=6 * 3600, show_spinner=False, max_entries=20)
def portfolio_review(facts: str, day: str) -> dict:
    """A short review of a personal portfolio, written only from its computed numbers."""
    prompt = f"""{STYLE}

Review this stock portfolio for its owner, the way a portfolio manager would summarize it in a monthly
report. Today is {day}. Use only the numbers below.

PORTFOLIO DATA (computed by the app):
{facts}

Return JSON exactly like:
{{
  "headline": "one sentence verdict on how the portfolio is doing, with its return vs the S&P 500",
  "performance": "2-3 sentences: total return, time-weighted return vs the S&P 500 and what the gap means",
  "drivers": "2-3 sentences: which positions drove the result (contribution in dollars and % of the gain), which hurt",
  "risk": "2-3 sentences: concentration (largest weight, effective number of positions), beta, volatility, VaR in dollars",
  "diversification": "1-2 sentences on sector and correlation exposure given the holdings",
  "watch": ["2-3 things to monitor, e.g. a position's weight drifting up, upcoming earnings dates given"],
  "ideas": ["2-3 portfolio-construction ideas to consider (rebalancing, position limits, diversifying), framed as options, never as instructions to buy or sell a specific security"]
}}
Never invent numbers or events. This is an educational review, not personalized investment advice."""
    return _generate(prompt, temperature=0.3)


def stamp_6h(now) -> str:
    return f"{now:%Y-%m-%d}-{now.hour // 6}"


def digest(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:10]
