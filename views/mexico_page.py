"""México: Banxico dashboard, the YTD ranking of Mexican ADRs and local news."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

import mexico
import sources as src
import theme as T
from views.common import click


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception:
        return None


def render():
    T.show('<div class="amb-hero"><div><div class="amb-eyebrow">México</div><h1>Peso, rates &amp; Mexican stocks</h1>'
           '<div class="sub">Official Banxico data and the Mexican companies that trade in New York.</div></div></div>')

    bx = _safe(mexico.indicators) or {}
    S = mexico.SERIES
    fix = _safe(mexico.fix_history, 400)
    fed = _safe(src.fred, "DFEDTARU")

    # ---------------- key figures
    tiles = []
    if fix is not None and len(fix) > 1:
        chg = (fix.iloc[-1] / fix.iloc[-2] - 1) * 100
        tiles.append(T.tile("Dollar in pesos", f"{fix.iloc[-1]:.4f}", T.pill(chg), tick="FIX",
                            foot_l=f"{fix.index[-1]:%b %d} · up = weaker peso",
                            extra=f'<div class="spark">{T.spark(fix.iloc[-90:], color=T.C["mx"])}</div>'))
    for key, name, tick, note in (("target", "Banxico rate", "TARGET", "official"),
                                  ("inflation", "Inflation", "INPC", "annual"),
                                  ("cetes28", "CETES 28 days", "AUCTION", "weekly")):
        b = bx.get(S[key])
        if b:
            extra = ""
            if key == "target" and fed is not None:
                extra = f'<div class="amb-note" style="margin-top:6px">vs Fed: <b style="color:var(--text)">{b["value"] - fed.iloc[-1]:+.2f} pts</b></div>'
            if key == "inflation":
                extra = T.range_bar(1.5, 6.0, b["value"], "Banxico target 2–4%", fmt=lambda v: f"{v:.1f}%")
            tiles.append(T.tile(name, f"{b['value']:.2f}%", tick=tick,
                                foot_l=f"{note} · {b['date']:%b %d, %Y}", extra=extra))
    if tiles:
        T.show(T.grid(tiles))
    else:
        T.show('<div class="amb-empty">Banxico data unavailable right now. Check BANXICO_TOKEN in Secrets.</div>')

    # ---------------- charts, one at a time
    T.section("Charts", "Banxico SIE · FRED", "History")
    t1, t2, t3 = st.tabs(["Peso", "Policy rates", "Inflation"])
    with t1:
        if fix is not None:
            f = fix.iloc[-260:]
            fig = go.Figure(go.Scatter(x=f.index, y=f.values, mode="lines", line=dict(color=T.C["mx"], width=2),
                                       fill="tozeroy", fillcolor="rgba(46,197,161,.07)", name="FIX"))
            fig.update_yaxes(range=[f.min() * 0.985, f.max() * 1.015])
            T.plot(fig, 300, "Pesos per dollar, last 12 months")
            T.show('<div class="amb-note">Up means a weaker peso. Banxico FIX rate (series SF43718).</div>')
    with t2:
        tgt = _safe(mexico.series_history, "target", 3)
        if tgt is not None:
            fig = go.Figure()
            fig.add_scatter(x=tgt.index, y=tgt.values, mode="lines", line=dict(color=T.C["mx"], width=2, shape="hv"), name="Banxico")
            if fed is not None:
                fd = fed[fed.index >= tgt.index[0]]
                fig.add_scatter(x=fd.index, y=fd.values, mode="lines", line=dict(color=T.C["us"], width=2, shape="hv"), name="Fed (upper)")
            fig.update_yaxes(ticksuffix="%")
            T.plot(fig, 300, "Banxico vs Fed policy rate")
            T.show('<div class="amb-note">The gap is the "carry": the extra yield that attracts dollars into peso assets.</div>')
    with t3:
        inf = _safe(mexico.series_history, "inflation", 4)
        if inf is not None:
            fig = go.Figure()
            fig.add_hrect(y0=2, y1=4, fillcolor="rgba(232,176,75,.07)", line_width=0)
            fig.add_hline(y=3, line=dict(color=T.C["gold"], dash="dot", width=1))
            fig.add_bar(x=inf.index, y=inf.values, marker_color=[T.C["down"] if v > 4 else T.C["mx"] for v in inf.values])
            fig.update_yaxes(range=[max(0, inf.min() - 1), inf.max() + 0.6], ticksuffix="%")
            fig.update_layout(showlegend=False)
            T.plot(fig, 300, "Annual inflation vs the 3% ± 1 target")

    # ---------------- ranking (clickable rows, readable on a phone)
    T.section("Mexican stocks in New York", "YTD in dollars · click a row to analyze", "Ranking")
    try:
        with st.spinner("Ranking the Mexican ADRs..."):
            rows = mexico.leaderboard()
    except Exception as e:
        rows = []
        st.warning(f"Couldn't build the ranking right now ({e}).")
    if rows:
        top = max((abs(r["ytd"]) for r in rows if r["ytd"] is not None), default=1) or 1
        body = []
        for i, r in enumerate(rows, start=1):
            w = abs(r["ytd"]) / top * 100 if r["ytd"] is not None else 0
            body.append(
                f'<div class="amb-row {"top" if i <= 5 else ""}"{T.go_attr("t:" + r["symbol"])}>'
                f'<span class="rk">{i:02d}</span>'
                f'<div style="min-width:0"><div class="s">{r["symbol"]} <span class="amb-th" style="margin-left:4px">{T.esc(r["sector"])}</span></div>'
                f'<div class="n">{T.esc(r["name"])}</div></div>'
                f'<span class="p">{T.money(r["price"])} {T.pill(r["pct"])}</span>'
                f'<span class="y" style="color:var(--{T.tone(r["ytd"])})">{T.pct(r["ytd"])}</span>'
                f'<div class="bar"><i class="{"neg" if (r["ytd"] or 0) < 0 else ""}" style="width:{w:.0f}%"></i></div></div>')
        click(f'<div class="amb-rows">{"".join(body)}</div>', "mx_rank")
        T.show('<div class="amb-note">Gold numbers mark the top 5, which feed the Mexico watchlist. ADRs are priced in dollars, '
               'so they move with both the stock in Mexico and the peso.</div>')

    # ---------------- news
    T.section("Mexico headlines", "El Financiero · Google News", "News")
    news, failed = src.recent_headlines("MX")
    T.show(T.news_list(news, 15))
    if failed:
        T.show(f'<div class="amb-note">Feeds that didn\'t answer: {T.esc(", ".join(failed))}</div>')
    T.footer("Banxico SIE · INEGI · Finnhub · Twelve Data")
