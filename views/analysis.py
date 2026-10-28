"""Analysis: one stock in depth - chart, risk, valuation (DCF + multiples), news and an AI take."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import ai
import filings
import mexico
import quant as Q
import sources as src
import state
import theme as T
from views.common import name_of


def _pick() -> str | None:
    mx_syms, _ = state.mx_list()
    options = list(dict.fromkeys(st.session_state.wl_us + mx_syms))
    focus = st.session_state.get("focus")
    if focus and focus not in options:
        options = [focus] + options
    c1, c2 = st.columns([3, 1.2], gap="medium")
    with c1:
        sel = st.segmented_control("Stock", options, default=focus if focus in options else (options[0] if options else None),
                                   key=f"an_pick_{focus}", label_visibility="collapsed")
    with c2:
        other = st.text_input("Other ticker", placeholder="Any US ticker, e.g. NVDA", label_visibility="collapsed").upper().strip()
    sym = other or sel
    if sym and sym != focus:
        state.focus(sym)
    return sym


def render():
    sym = _pick()
    if not sym:
        T.show('<div class="amb-empty">Add stocks to your watchlist first.</div>')
        return
    market = state.market_of(sym)
    q = src.try_quote(sym)
    if not q:
        st.error(f"No quote for {sym}. Check the ticker (US-listed only).")
        return
    prof = src.profile(sym)
    is_open = src.us_market_status()["open"]
    er = src.next_earnings(sym)

    T.show(f"""
    <div class="amb-hero" style="margin-top:14px">
      <div style="display:flex;gap:16px;align-items:center">{T.logo(prof['logo'], sym, 56)}
        <div><div class="amb-kicker">{T.esc(prof['industry'] or 'Stock')} · {('NYSE-listed ADR' if market == 'MX' else 'US-listed')}</div>
        <h1 style="font-size:clamp(1.8rem,3.6vw,2.7rem)">{T.esc(name_of(sym))} <span style="color:var(--muted);font-weight:500">{T.esc(sym)}</span></h1>
        <div class="sub">{T.chip(market, market)}<span>{T.freshness(q['time'], is_open)}</span>
        <span>{('Next earnings ' + er['date'] + (' · ' + er['when'] if er['when'] else '')) if er else 'No earnings date announced'}</span></div></div>
      </div>
      <div style="text-align:right"><div style="font-family:var(--mono);font-size:2.3rem;color:var(--text)">{T.money(q['price'])}</div>
        <div>{T.pill(q['pct'])} <span style="font-family:var(--mono);color:var(--muted);font-size:.8rem">{T.clock(q['time'])} ET</span></div></div>
    </div>""")

    with st.spinner("Loading two years of prices (free plan: 8 requests per minute)..."):
        h = src.try_history(sym)
        spy = src.try_history("SPY")
    if h is None:
        st.warning("Price history isn't available right now (Twelve Data limit). Refresh in a minute.")
        return
    close = h["close"].copy()
    if close.index[-1].date() < q["time"].date():  # extend with today's live price
        close.loc[pd.Timestamp(q["time"].date())] = q["price"]
    rf, rf_label = src.risk_free()
    vol = Q.annual_volatility(close)
    m = {
        "ytd": Q.ytd_return(close), "r1y": Q.period_return(close, 365), "vol": vol, "mdd": Q.max_drawdown(close),
        "beta": Q.beta(close, spy["close"]) if spy is not None else None, "sharpe": Q.sharpe(close, rf),
        "trend": Q.trend_label(close),
    }
    T.show(T.kv([
        ("YTD return", f'<span style="color:var(--{T.tone(m["ytd"])})">{T.pct(m["ytd"])}</span>', "since Dec 31 close"),
        ("1-year return", T.pct(m["r1y"]), ""),
        ("Volatility", T.pct(vol, 1, signed=False), "annualized, 1 year of daily moves"),
        ("Max drawdown", T.pct(m["mdd"]), "worst peak-to-trough, 1 year"),
        ("Beta vs S&P 500", f'{m["beta"]:.2f}' if m["beta"] is not None else "—", "2 years of weekly returns"),
        ("Sharpe ratio", f'{m["sharpe"]:.2f}' if m["sharpe"] is not None else "—", "1 year, vs 10Y Treasury"),
    ]))

    ctx = {"sym": sym, "q": q, "m": m, "rf": rf, "prof": prof, "er": er, "market": market}
    t1, t2, t3, t4 = st.tabs(["Chart & risk", "Valuation", "News", "Our take"])
    with t1:
        _chart_tab(sym, h, close, q, m, vol, ctx)
    with t2:
        _valuation_tab(sym, q, m, rf, rf_label, close, market, ctx)
    with t3:
        try:
            news = src.company_news(sym)
        except Exception:
            news = []
        ctx["news"] = news
        T.show(T.news_list(news, 12))
    with t4:
        _take_tab(sym, ctx)
    T.footer("Not investment advice · statistics describe the past, they don't predict the future")


# --------------------------------------------------------------------------- chart & risk
def _chart_tab(sym, h, close, q, m, vol, ctx):
    span = st.segmented_control("Range", ["3M", "6M", "1Y", "2Y"], default="1Y", key="span", label_visibility="collapsed")
    days = {"3M": 92, "6M": 183, "1Y": 365, "2Y": 760}[span or "1Y"]
    s50, s200 = Q.sma(close, 50), Q.sma(close, 200)
    cut = close.index[-1] - pd.Timedelta(days=days)
    c, hh = close[close.index >= cut], h[h.index >= cut]
    up = c.iloc[-1] >= c.iloc[0]
    col = T.C["up"] if up else T.C["down"]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.78, 0.22], vertical_spacing=0.03)
    fig.add_scatter(x=c.index, y=c.values, mode="lines", name=sym, line=dict(color=col, width=2),
                    fill="tozeroy", fillcolor=("rgba(43,214,123,.07)" if up else "rgba(255,92,108,.07)"), row=1, col=1)
    fig.add_scatter(x=s50[s50.index >= cut].index, y=s50[s50.index >= cut].values, name="50-day avg",
                    line=dict(color=T.C["gold"], width=1.2, dash="dot"), row=1, col=1)
    fig.add_scatter(x=s200[s200.index >= cut].index, y=s200[s200.index >= cut].values, name="200-day avg",
                    line=dict(color=T.C["us"], width=1.2, dash="dot"), row=1, col=1)
    if "volume" in hh:
        fig.add_bar(x=hh.index, y=hh["volume"], name="Volume", marker_color=T.C["line2"], row=2, col=1, showlegend=False)
    fig.update_yaxes(range=[c.min() * 0.95, c.max() * 1.04], row=1, col=1)
    fig.update_yaxes(showticklabels=False, row=2, col=1)
    T.plot(fig, 440)
    T.show(f'<div class="amb-note"><span class="amb-tag calc">Calc</span>{T.esc(m["trend"])}.</div>')

    st.write("")
    a, b = st.columns([1.25, 1], gap="large")
    with a:
        T.section("Statistical price ranges")
        if vol:
            rows = []
            ranges = {}
            for label, d in (("1 month", 21), ("3 months", 63), ("6 months", 126)):
                r = Q.statistical_range(q["price"], vol, d)
                ranges[label] = r
                rows.append(f'<tr><td>{label}</td><td class="num">{T.money(r.low68)} – {T.money(r.high68)}</td>'
                            f'<td class="num">{T.money(r.low95)} – {T.money(r.high95)}</td></tr>')
            ctx["ranges"] = ranges
            T.show(f'<div class="amb-wrap"><table class="amb-lb"><thead><tr><th>Horizon</th><th class="num">68% of the time</th>'
                   f'<th class="num">95% of the time</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
                   f'<div class="amb-note"><span class="amb-tag calc">Calc</span>Where the price would land if the coming months are as '
                   f'volatile as the last year ({T.pct(vol, 0, signed=False)} a year), with no drift up or down. '
                   f'A statistical range, not a forecast or a target.</div>')
    with b:
        T.section("Drawdown · 1 year")
        dd = Q.drawdown_series(close.iloc[-252:])
        fig = go.Figure(go.Scatter(x=dd.index, y=dd.values * 100, mode="lines", line=dict(color=T.C["down"], width=1.6),
                                   fill="tozeroy", fillcolor="rgba(255,92,108,.12)", name="Drawdown"))
        fig.update_yaxes(ticksuffix="%")
        fig.update_layout(margin=dict(l=8, r=16, t=10, b=8))
        T.plot(fig, 230)


# --------------------------------------------------------------------------- valuation
def _multiples(sym, ctx):
    try:
        km = src.key_metrics(sym)
    except Exception:
        km = {}
    ctx["multiples"] = km
    T.section("Multiples", "Finnhub · trailing twelve months")
    T.show(T.kv([
        ("P/E", T.mult(km.get("pe")), "price / earnings"),
        ("Forward P/E", T.mult(km.get("fwd_pe")), "on expected earnings"),
        ("P/S", T.mult(km.get("ps")), "price / sales"),
        ("EV/EBITDA", T.mult(km.get("ev_ebitda")), "enterprise value / EBITDA"),
        ("EV/FCF", T.mult(km.get("ev_fcf")), "enterprise value / free cash flow"),
        ("Net margin", T.pct(km.get("net_margin"), 1, False, frac=False), ""),
        ("ROE", T.pct(km.get("roe"), 1, False, frac=False), "return on equity"),
        ("Revenue growth", T.pct(km.get("rev_growth"), 1, True, frac=False), "year over year"),
    ]))


def _valuation_tab(sym, q, m, rf, rf_label, close, market, ctx):
    price = q["price"]
    try:
        if market == "MX":
            raise filings.FilingsError(
                "Mexican companies file a 20-F in IFRS and pesos, and each ADR represents several local shares, "
                "so the automatic DCF is limited to US filers. The multiples below still work.")
        with st.spinner("Reading the 10-K data from the SEC..."):
            f = filings.build(src.sec_facts(sym))
    except Exception as e:
        T.show(f'<div class="amb-empty" style="text-align:left">DCF not available for {T.esc(sym)}: {T.esc(str(e))}</div>')
        _multiples(sym, ctx)
        return

    fcf = f["fcf"]
    T.section("Discounted cash flow", f"SEC 10-K data · balance sheet {f['balance_date'] or 'n/a'}")
    c1, c2, c3, c4 = st.columns(4, gap="small")
    with c1:
        base_mode = st.selectbox("Starting free cash flow", ["Latest year", "3-year average", "Manual"], key=f"fcfm_{sym}")
    if base_mode == "Latest year":
        fcf0 = float(fcf.iloc[-1])
    elif base_mode == "3-year average":
        fcf0 = float(fcf.iloc[-3:].mean())
    else:
        with c1:
            fcf0 = st.number_input("FCF ($ millions)", value=float(max(fcf.iloc[-1], 0) / 1e6), step=100.0, key=f"fcfv_{sym}") * 1e6
    rev_cagr = Q.cagr(f["revenue"]) if not f["revenue"].empty else None
    g_default = float(np.clip(rev_cagr if rev_cagr is not None else 0.06, -0.05, 0.25))
    wacc_default = float(np.clip(Q.cost_of_equity(rf, m["beta"]), 0.07, 0.14))
    with c2:
        g = st.slider("Growth, years 1-5", -10.0, 40.0, round(g_default * 100, 1), 0.5, key=f"g_{sym}",
                      help="Default: 5-year revenue growth, capped at 25%. Years 6-10 fade to the terminal rate.") / 100
    with c3:
        wacc = st.slider("Discount rate (WACC)", 5.0, 16.0, round(wacc_default * 100, 1), 0.25, key=f"w_{sym}",
                         help=f"Default: CAPM = risk-free + beta × 5% equity premium. {rf_label}") / 100
    with c4:
        tg = st.slider("Terminal growth", 0.0, 4.0, 2.5, 0.25, key=f"tg_{sym}") / 100

    if fcf0 <= 0:
        T.show(f'<div class="amb-empty" style="text-align:left">The starting free cash flow is {T.big(fcf0)}. A DCF on negative cash flow '
               f'gives a meaningless value. Try the 3-year average or type a "normalized" figure in Manual.</div>')
        _fcf_chart(f)
        _multiples(sym, ctx)
        return
    if wacc <= tg + 0.005:
        st.error("The discount rate has to be clearly above terminal growth.")
        return

    base = Q.dcf(fcf0, g, wacc, tg, f["net_debt"], f["shares"])
    bear = Q.dcf(fcf0, g * 0.5 if g > 0 else g * 1.5, min(wacc + 0.01, 0.2), tg, f["net_debt"], f["shares"])
    bull = Q.dcf(fcf0, min(g * 1.5, 0.45) if g > 0 else g * 0.5, max(wacc - 0.01, tg + 0.01), tg, f["net_debt"], f["shares"])
    label, gap = Q.verdict(base["per_share"], price)
    implied = Q.implied_growth(price, fcf0, wacc, tg, f["net_debt"], f["shares"])
    cls = {"Undervalued": "under", "Overvalued": "over"}.get(label, "fair")
    ctx["dcf"] = {"value": base["per_share"], "bear": bear["per_share"], "bull": bull["per_share"], "verdict": label,
                  "gap": gap, "implied_g": implied, "g": g, "wacc": wacc, "tg": tg, "fcf0": fcf0}

    T.show(f"""
    <div class="amb-verdict {cls}" style="margin-top:10px">
      <div><div class="amb-kicker" style="margin-bottom:4px">Base case</div><div class="big">{label}</div>
        <div class="amb-note" style="margin-top:4px">Intrinsic value {T.pct(gap, 0)} vs the market price</div></div>
      <div class="nums">
        <div><div class="k">Intrinsic value</div><div class="v">{T.money(base['per_share'])}</div></div>
        <div><div class="k">Market price</div><div class="v">{T.money(price)}</div></div>
        <div><div class="k">Bear / Bull</div><div class="v">{T.money(bear['per_share'])} / {T.money(bull['per_share'])}</div></div>
        <div><div class="k">Price implies</div><div class="v">{(T.pct(implied, 1) + ' growth') if implied is not None else '—'}</div></div>
      </div>
    </div>""")
    T.show(f'<div class="amb-note"><span class="amb-tag calc">Calc</span>Reverse DCF: at {T.pct(wacc, 1, False)} WACC, the current price '
           f'only makes sense if free cash flow grows about {T.pct(implied, 1) if implied is not None else "n/a"} a year for five years. '
           f'Terminal value is {T.pct(base["terminal_share"], 0, False)} of the enterprise value.</div>')

    st.write("")
    a, b = st.columns([1.35, 1], gap="large")
    with a:
        T.section("Football field", "value ranges vs today's price")
        bars = []
        if close is not None and len(close) > 200:
            bars.append(("52-week range", close.iloc[-252:].min(), close.iloc[-252:].max(), T.C["us"]))
        if m["vol"]:
            r = Q.statistical_range(price, m["vol"], 63)
            bars.append(("3-month stat. range (95%)", r.low95, r.high95, "#C792EA"))
        waccs = [wacc - 0.01, wacc - 0.005, wacc, wacc + 0.005, wacc + 0.01]
        tgs = [tg - 0.005, tg, tg + 0.005]
        sens = Q.sensitivity(fcf0, g, f["net_debt"], f["shares"], waccs, tgs)
        bars.append(("DCF sensitivity (WACC ±1, g ±0.5)", np.nanmin(sens.values), np.nanmax(sens.values), T.C["gold"]))
        bars.append(("DCF bear → bull", bear["per_share"], bull["per_share"], T.C["mx"]))
        fig = go.Figure()
        for i, (lbl, lo, hi, colr) in enumerate(bars):
            fig.add_trace(go.Bar(y=[lbl], x=[hi - lo], base=[lo], orientation="h", marker=dict(color=colr, opacity=.75),
                                 hovertemplate=f"{lbl}<br>${lo:,.2f} – ${hi:,.2f}<extra></extra>", showlegend=False))
        fig.add_vline(x=price, line=dict(color=T.C["text"], width=1.5, dash="dash"),
                      annotation_text=f"Price {T.money(price)}", annotation_font_color=T.C["text"])
        fig.update_layout(bargap=0.45, hovermode="closest", margin=dict(l=8, r=16, t=30, b=8))
        fig.update_xaxes(tickprefix="$", gridcolor=T.C["line"])
        fig.update_yaxes(side="left", tickfont=dict(family="Inter", color=T.C["text2"]))
        T.plot(fig, 300)
    with b:
        T.section("Sensitivity", "value per share")
        tbl = sens.copy()
        tbl.index = [f"WACC {w * 100:.2f}%" for w in tbl.index]
        tbl.columns = [f"g {t * 100:.2f}%" for t in tbl.columns]
        def shade(v):
            if not T.is_num(v):
                return ""
            a = min(abs(v / price - 1) / 0.5, 1) * 0.45 + 0.08
            return f"background-color: rgba({'43,214,123' if v >= price else '255,92,108'},{a:.2f}); color: #E9EEF4"
        st.dataframe(tbl.style.format("${:,.2f}").map(shade), use_container_width=True)
        T.show(f'<div class="amb-note">Green cells are above today\'s price ({T.money(price)}), red below.</div>')

    _fcf_chart(f)
    with st.expander("Projection, inputs and data notes"):
        flows = pd.DataFrame(base["flows"])
        flows["growth"] = flows["growth"].map(lambda x: f"{x * 100:.1f}%")
        flows["fcf"] = flows["fcf"].map(T.big)
        flows["pv"] = flows["pv"].map(T.big)
        st.dataframe(flows.rename(columns={"year": "Year", "growth": "Growth", "fcf": "Free cash flow", "pv": "Present value"}),
                     hide_index=True, use_container_width=True)
        T.show(T.kv([
            ("Starting FCF", T.big(fcf0), base_mode), ("Net debt", T.big(f["net_debt"]), "debt minus cash & short-term investments"),
            ("Shares", f"{f['shares'] / 1e6:,.0f}M", f["shares_source"]), ("Enterprise value", T.big(base["ev"]), ""),
            ("Equity value", T.big(base["equity"]), ""), ("Revenue CAGR", T.pct(rev_cagr), "last 5 fiscal years"),
        ]))
        for n in f["notes"]:
            st.caption("• " + n)
    _multiples(sym, ctx)


def _fcf_chart(f):
    T.section("Revenue and free cash flow", "fiscal years, SEC 10-K")
    fig = go.Figure()
    if not f["revenue"].empty:
        fig.add_bar(x=f["revenue"].index.year, y=f["revenue"].values / 1e9, name="Revenue", marker_color=T.C["line2"])
    fig.add_bar(x=f["fcf"].index.year, y=f["fcf"].values / 1e9, name="Free cash flow",
                marker_color=[T.C["mx"] if v >= 0 else T.C["down"] for v in f["fcf"].values])
    fig.update_yaxes(ticksuffix="B", tickprefix="$")
    fig.update_layout(barmode="group", hovermode="x unified")
    T.plot(fig, 280)


# --------------------------------------------------------------------------- AI take
def _facts(ctx) -> str:
    q, m, p = ctx["q"], ctx["m"], ctx["prof"]
    lines = [f"Company: {name_of(ctx['sym'])} ({ctx['sym']}), industry: {p['industry'] or 'n/a'}, "
             f"{'Mexican company, NYSE-listed ADR' if ctx['market'] == 'MX' else 'US-listed'}",
             f"Price: {q['price']:.2f} ({q['pct']:+.2f}% today)",
             f"YTD return: {T.pct(m['ytd'])}; 1-year: {T.pct(m['r1y'])}; annualized volatility: {T.pct(m['vol'], 1, False)}; "
             f"1-year max drawdown: {T.pct(m['mdd'])}; beta vs S&P 500: {m['beta'] if m['beta'] is None else round(m['beta'], 2)}; "
             f"Sharpe: {m['sharpe'] if m['sharpe'] is None else round(m['sharpe'], 2)}",
             f"Trend: {m['trend']}"]
    if ctx.get("ranges"):
        r = ctx["ranges"]["3 months"]
        lines.append(f"3-month statistical range (68%): {r.low68:.2f}-{r.high68:.2f}; (95%): {r.low95:.2f}-{r.high95:.2f}")
    km = ctx.get("multiples") or {}
    if km:
        lines.append("Multiples: " + ", ".join(f"{k}={v:.2f}" for k, v in km.items() if v is not None))
    d = ctx.get("dcf")
    if d:
        lines.append(f"DCF (user assumptions: growth {d['g']:.1%}, WACC {d['wacc']:.1%}, terminal {d['tg']:.1%}): "
                     f"value {d['value']:.2f} per share, bear {d['bear']:.2f}, bull {d['bull']:.2f} -> {d['verdict']} "
                     f"({d['gap']:+.0%} vs price). Reverse DCF: price implies {('%.1f%%' % (d['implied_g'] * 100)) if d['implied_g'] is not None else 'n/a'} "
                     "annual FCF growth for 5 years.")
    else:
        lines.append("DCF: not available for this company.")
    if ctx.get("er"):
        lines.append(f"Next earnings date: {ctx['er']['date']} {ctx['er']['when']}")
    return "\n".join(lines)


def _take_tab(sym, ctx):
    T.show('<div class="amb-note" style="margin:6px 0 12px"><span class="amb-tag data">Data</span>fetched '
           '<span class="amb-tag calc">Calc</span>computed by the app <span class="amb-tag ai">AI</span>Gemini\'s reading of both</div>')
    key = f"take_{sym}"
    if st.button("Write our take", type="primary", key=f"btn_{key}") or key in st.session_state:
        news = ctx.get("news") or []
        try:
            with st.spinner("Gemini is reading the numbers..."):
                t = ai.stock_take(sym, _facts(ctx),
                                  tuple(f"{n['source']} | {n['time']:%b %d} | {n['title']} — {n['summary'][:200]}" for n in news[:10] if n.get("time")),
                                  dt.date.today().isoformat())
            st.session_state[key] = True
        except Exception as e:
            st.info(f"The AI take isn't available right now ({e}).")
            return
        blocks = [("Situation", t.get("situation")), ("Momentum", t.get("momentum")), ("Valuation", t.get("valuation"))]
        T.show('<div class="amb-brief">' + "".join(
            f'<div class="amb-take"><div class="h"><span class="amb-tag ai">AI</span>{k}</div><p>{T.esc(v or "")}</p></div>'
            for k, v in blocks) + "</div>")
        st.write("")
        sc = [("Bull", t.get("bull"), "up"), ("Base", t.get("base"), "flat"), ("Bear", t.get("bear"), "down")]
        T.show('<div class="amb-grid g3">' + "".join(
            f'<div class="amb-story"><div class="top"><span class="amb-pill {c}">{k} case</span></div>'
            f'<div class="row">{T.esc(v or "")}</div></div>' for k, v, c in sc) + "</div>")
        st.write("")
        lists = [("Risks", t.get("risks")), ("Catalysts", t.get("catalysts")), ("What the data can't tell us", t.get("unknowns"))]
        T.show('<div class="amb-grid g3">' + "".join(
            f'<div class="amb-take"><div class="h">{k}</div><p>{"<br>".join("• " + T.esc(str(x)) for x in (v or []))}</p></div>'
            for k, v in lists) + "</div>")
        T.show(f'<div class="amb-lead" style="margin-top:20px;font-size:1.3rem"><span>›</span> {T.esc(t.get("bottom_line", ""))}</div>')
        T.show('<div class="amb-note">An AI reading of the data above, not a recommendation to buy or sell.</div>')
    else:
        T.show('<div class="amb-empty">Click the button for a written take: situation, bull/base/bear cases, risks and catalysts, '
               'built only from the numbers on this page and recent news.</div>')
