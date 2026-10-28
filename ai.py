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


def _generate(prompt: str, temperature: float = 0.3) -> dict:
    if src.DEMO:
        import demo
        return demo.fake_ai(prompt)
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    last = "no model tried"
    for model in models()[:4]:  # busy (503), retired (404) or out of quota (429): try the next one
        try:
            r = requests.post(f"{API}/models/{model}:generateContent", json=body,
                              headers={"x-goog-api-key": _key()}, timeout=60)
        except requests.RequestException as e:
            last = f"{model}: {e.__class__.__name__}"
            continue
        if r.status_code in (404, 429, 500, 503):
            last = f"{model} returned {r.status_code}"
            continue
        if r.status_code >= 400:
            raise AIError(f"Gemini returned an error ({r.status_code}).")
        try:
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip()).strip())
        except Exception:
            last = f"{model}: unreadable answer"
            continue
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
      "sources": [headline numbers that support this story]}}
  ]
}}
Pick 6 stories, ranked by market importance, at least 2 about Mexico if the headlines allow.
Merge headlines about the same event into one story and cite all of them."""
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
def stock_take(symbol: str, facts: str, news: tuple[str, ...], day: str) -> dict:
    numbered = "\n".join(f"[{i}] {h}" for i, h in enumerate(news)) or "(no recent company news)"
    prompt = f"""{STYLE}

Give your take on {symbol} for an investor deciding whether to dig deeper.

DATA AND CALCULATIONS FROM THE APP (treat as facts):
{facts}

RECENT NEWS:
{numbered}

Return JSON exactly like:
{{
  "situation": "2-3 sentences: what is going on with the stock now",
  "momentum": "1-2 sentences on the price trend and volatility, citing the numbers given",
  "valuation": "1-2 sentences on what the multiples and the DCF (if given) imply",
  "bull": "the bull case and the assumption it needs",
  "base": "the base case and its assumption",
  "bear": "the bear case and what would trigger it",
  "risks": ["3 short risks"],
  "catalysts": ["up to 3 upcoming events; only ones supported by the inputs, e.g. the earnings date"],
  "unknowns": ["1-2 things the data can't tell us"],
  "bottom_line": "one sentence, not a buy/sell recommendation"
}}"""
    return _generate(prompt, temperature=0.35)


def stamp_6h(now) -> str:
    return f"{now:%Y-%m-%d}-{now.hour // 6}"


def digest(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:10]
