"""México: Banxico dashboard, the YTD leaderboard of Mexican ADRs and local news."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

import mexico
import sources as src
import state
import theme as T
from views.common import analyze_picker


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception:
        return None


def render():
    T.show('<div class="amb-hero"><div><div class="amb-kicker">México</div><h1>Peso, rates &amp; Mexican stocks</h1>'
           '<div class="sub">Official Banxico data plus the Mexican companies that trade in New York.</div></div></div>')

    bx = _safe(mexico.indicators) or {}
    S = mexico.SERIES
    fix = _safe(mexico.fix_history, 400)

    # ---------------- key figures
    def val(k, unit="%", dec=2):
        b = bx.get(S[k])
        return (f"{b['value']:.{dec}f}{unit}", f"{b['date']:%b %d, %Y}") if b else ("—", "unavailable")

    items = []
    if fix is not None:
        items.append(("USD/MXN FIX", f"{fix.iloc[-1]:.4f}", f"{fix.index[-1]:%b %d, %Y}"))
    for k, lbl in (("target", "Banxico target rate"), ("tiie28", "TIIE 28 days"),
                   ("cetes28", "CETES 28 days"), ("inflation", "Annual inflation")):
        v, d = val(k)
        items.append((lbl, v, d))
    T.show(T.kv(items))

    # ---------------- charts
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        if fix is not None:
            f = fix.iloc[-260:]
            fig = go.Figure(go.Scatter(x=f.index, y=f.values, mode="lines", line=dict(color=T.C["mx"], width=2),
                                       fill="tozeroy", fillcolor="rgba(46,197,161,.08)", name="FIX"))
            fig.update_yaxes(range=[f.min() * 0.985, f.max() * 1.015])
            fig.update_layout(title=dict(text="Dollar in pesos · last 12 months", font=dict(size=14, color=T.C["text"])))
            T.plot(fig, 320)
            T.show('<div class="amb-note">Up means a weaker peso. Source: Banxico FIX (SF43718).</div>')
    with c2:
        tgt = _safe(mexico.series_history, "target", 3)
        fed = _safe(src.fred, "DFEDTARU")
        if tgt is not None:
            fig = go.Figure()
            fig.add_scatter(x=tgt.index, y=tgt.values, mode="lines", line=dict(color=T.C["mx"], width=2, shape="hv"), name="Banxico")
            if fed is not None:
                fd = fed[fed.index >= tgt.index[0]]
                fig.add_scatter(x=fd.index, y=fd.values, mode="lines", line=dict(color=T.C["us"], width=2, shape="hv"), name="Fed (upper)")
            fig.update_layout(title=dict(text="Policy rates · Banxico vs Fed", font=dict(size=14, color=T.C["text"])))
            T.plot(fig, 320)
            T.show('<div class="amb-note">The gap between the two is the "carry" that attracts dollars to peso assets.</div>')

    inf = _safe(mexico.series_history, "inflation", 4)
    if inf is not None:
        fig = go.Figure()
        fig.add_hrect(y0=2, y1=4, fillcolor="rgba(232,176,75,.07)", line_width=0)
        fig.add_hline(y=3, line=dict(color=T.C["gold"], dash="dot", width=1))
        fig.add_bar(x=inf.index, y=inf.values, marker_color=[T.C["down"] if v > 4 else T.C["mx"] for v in inf.values], name="Inflation")
        fig.update_layout(title=dict(text="Annual inflation vs Banxico's 3% ± 1 target", font=dict(size=14, color=T.C["text"])), showlegend=False)
        fig.update_yaxes(range=[max(0, inf.min() - 1), inf.max() + 0.6], ticksuffix="%")
        T.plot(fig, 300)

    # ---------------- leaderboard
    T.section("Mexican stocks in New York · YTD ranking", "price: Finnhub · base: Dec 31 close, Twelve Data", T.chip("MX", "MX"))
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
            neg = " neg" if (r["ytd"] or 0) < 0 else ""
            body.append(
                f'<tr class="{"top" if i <= 5 else ""}"><td class="rk">{i:02d}</td>'
                f'<td><b style="color:var(--text);font-family:var(--display)">{r["symbol"]}</b><br>'
                f'<span style="font-size:.78rem;color:var(--muted)">{T.esc(r["name"])} · {T.esc(r["sector"])}</span></td>'
                f'<td class="num">{T.money(r["price"])}</td><td class="num">{T.pill(r["pct"]) if r["pct"] is not None else "—"}</td>'
                f'<td class="num" style="min-width:90px">{T.pct(r["ytd"])}</td>'
                f'<td style="width:28%"><div class="bar{neg}" style="width:{w:.0f}%"></div></td></tr>')
        T.show(f'<div class="amb-wrap"><table class="amb-lb"><thead><tr><th>#</th><th>Company</th><th class="num">Price</th>'
               f'<th class="num">Today</th><th class="num">YTD</th><th></th></tr></thead><tbody>{"".join(body)}</tbody></table></div>')
        mx_syms, follows = state.mx_list()
        note = ("Your Mexico watchlist follows this top 5 automatically."
                if follows else "Your Mexico watchlist is custom. Reset it on the Watchlist page to follow this top 5.")
        T.show(f'<div class="amb-note">Gold rank numbers mark the top 5. {note} ADR prices move with both the '
               f'stock in Mexico and the peso.</div>')
        analyze_picker([r["symbol"] for r in rows], "pick_mx", "Analyze one")

    # ---------------- news
    T.section("Mexico headlines", "El Financiero · Google News")
    news, failed = src.recent_headlines("MX")
    T.show(T.news_list(news, 15))
    if failed:
        T.show(f'<div class="amb-note">Feeds that didn\'t answer: {T.esc(", ".join(failed))}</div>')
    T.footer("Banxico SIE · INEGI · Finnhub · Twelve Data")
