"""Analysis: one stock in depth - chart & risk, valuation, financials, outlook, compare, research note, news."""
from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import quant as Q
import sources as src
import state
import theme as T
from views import compare, financials, outlook, research, valuation_tab
from views.common import name_of


# --------------------------------------------------------------------------- picker
def _on_select(key: str):
    v = st.session_state.get(key)
    if v:
        state.focus(v)
    st.session_state["an_other"] = ""


def _pick() -> str | None:
    options = state.all_symbols()
    focus = st.session_state.get("focus") or (options[0] if options else None)
    if focus and focus not in options:
        options = [focus] + options
    if focus and not st.session_state.get("focus"):
        state.focus(focus)
    key = f"an_sel_{focus}"
    st.selectbox("Your stocks (or use the search box at the top for any company)", options,
                 index=options.index(focus) if focus in options else 0,
                 format_func=lambda s: f"{s} · {name_of(s)}", key=key, on_change=_on_select, args=(key,))
    return focus


def render():
    sym = _pick()
    if not sym:
        return
    market = state.market_of(sym)
    etf_or_mx = src.is_etf(sym) or market == "MX"
    src.prefetch([(src.try_quote, sym), (src.profile, sym), (src.us_market_status,), (src.next_earnings, sym),
                  (src.company_news, sym), (src.key_metrics, sym), (src.recommendations, sym), (src.risk_free,),
                  (src.peer_multiples, sym), None if etf_or_mx else (src.sec_facts, sym),
                  (src.try_history, sym), (src.try_history, "SPY")])
    q = src.try_quote(sym)
    if not q:
        st.error(f"No quote for {sym}. Check the ticker (US-listed stocks, ADRs and ETFs).")
        return
    prof = src.profile(sym)
    is_open = src.us_market_status()["open"]
    er = src.next_earnings(sym)
    kind = "ETF" if src.is_etf(sym) else ("NYSE-listed Mexican ADR" if market == "MX" else "US-listed stock")

    T.show(f"""
    <div class="amb-hero" style="margin-top:6px">
      <div style="display:flex;gap:14px;align-items:center;min-width:0">{T.logo(prof['logo'], sym, 52)}
        <div style="min-width:0"><div class="amb-eyebrow">{(T.esc(prof['industry']) + ' · ') if prof['industry'] else ''}{kind}</div>
        <h1 style="font-size:clamp(1.6rem,3.4vw,2.5rem)">{T.esc(name_of(sym))} <span style="color:var(--muted);font-weight:500">{T.esc(sym)}</span></h1>
        <div class="sub">{T.chip(market, market)}<span>{T.status(q['time'], is_open)}</span>
        <span>{('Next earnings ' + er['date'] + (' · ' + er['when'] if er['when'] else '')) if er else 'No earnings date announced'}</span></div></div>
      </div>
      <div style="text-align:right"><div style="font-family:var(--display);font-size:2.4rem;font-weight:500;color:var(--text)">{T.money(q['price'])}</div>
        <div>{T.pill(q['pct'])}</div></div>
    </div>""")

    with st.spinner("Loading two years of prices (free plan: 8 requests per minute)..."):
        h = src.try_history(sym)
        spy = src.try_history("SPY")
    if h is None:
        st.warning("Price history isn't available right now (Twelve Data limit). Refresh in a minute.")
        return
    close = h["close"].copy()
    if close.index[-1].date() < q["time"].date():
        close.loc[pd.Timestamp(q["time"].date())] = q["price"]
    rf, rf_label = src.risk_free()
    vol = Q.annual_volatility(close)
    m = {"ytd": Q.ytd_return(close), "r1y": Q.period_return(close, 365), "vol": vol, "mdd": Q.max_drawdown(close),
         "beta": Q.beta(close, spy["close"]) if spy is not None else None, "sharpe": Q.sharpe(close, rf),
         "trend": Q.trend_label(close)}
    T.show(T.kv([
        ("YTD return", f'<span style="color:var(--{T.tone(m["ytd"])})">{T.pct(m["ytd"])}</span>', "since Dec 31 close"),
        ("1-year return", T.pct(m["r1y"]), ""),
        ("Volatility", T.pct(vol, 1, signed=False), "annualized"),
        ("Max drawdown", T.pct(m["mdd"]), "worst fall, 1 year"),
        ("Beta", f'{m["beta"]:.2f}' if m["beta"] is not None else "—", "vs S&P 500, 2y weekly"),
        ("Sharpe", f'{m["sharpe"]:.2f}' if m["sharpe"] is not None else "—", "1 year, vs 10Y"),
    ]))

    ctx = {"sym": sym, "q": q, "m": m, "rf": rf, "prof": prof, "er": er, "market": market}
    try:
        news = src.company_news(sym)
    except Exception:
        news = []
    ctx["news"] = news
    t_chart, t_val, t_fin, t_out, t_cmp, t_note, t_news = st.tabs(
        ["Chart & risk", "Valuation", "Financials", "Outlook", "Compare", "Research note", "News"])
    # Order matters: later tabs (and the research note) use what earlier ones computed.
    with t_chart:
        _chart_tab(sym, h, close, q, m, vol, ctx)
    with t_val:
        valuation_tab.render(sym, q, m, rf, rf_label, close, market, ctx)
    with t_fin:
        financials.render(sym, ctx)
    with t_out:
        outlook.render(sym, close, q, ctx)
    with t_cmp:
        compare.render(sym, close, prof, rf, market, ctx)
    with t_note:
        research.render(sym, ctx)
    with t_news:
        T.show(T.news_list(news, 12))
    T.footer("Not investment advice · statistics describe the past, they don't predict the future")


# --------------------------------------------------------------------------- chart & risk
def _chart_tab(sym, h, close, q, m, vol, ctx):
    span = st.segmented_control("Range", ["3M", "6M", "1Y", "2Y"], default="1Y", key="span", label_visibility="collapsed")
    days = {"3M": 92, "6M": 183, "1Y": 365, "2Y": 760}[span or "1Y"]
    s50, s200 = Q.sma(close, 50), Q.sma(close, 200)
    cut = close.index[-1] - pd.Timedelta(days=days)
    c, hh = close[close.index >= cut], h[h.index >= cut]
    up = c.iloc[-1] >= c.iloc[0]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.8, 0.2], vertical_spacing=0.03)
    fig.add_scatter(x=c.index, y=c.values, mode="lines", name=sym, line=dict(color=T.C["up"] if up else T.C["down"], width=2),
                    fill="tozeroy", fillcolor=(T.rgba("up", .06) if up else T.rgba("down", .06)), row=1, col=1)
    fig.add_scatter(x=s50[s50.index >= cut].index, y=s50[s50.index >= cut].values, name="50-day avg",
                    line=dict(color=T.C["gold"], width=1.2, dash="dot"), row=1, col=1)
    fig.add_scatter(x=s200[s200.index >= cut].index, y=s200[s200.index >= cut].values, name="200-day avg",
                    line=dict(color=T.C["us"], width=1.2, dash="dot"), row=1, col=1)
    if "volume" in hh:
        fig.add_bar(x=hh.index, y=hh["volume"], marker_color=T.C["line2"], row=2, col=1, showlegend=False, name="Volume")
    fig.update_yaxes(range=[c.min() * 0.95, c.max() * 1.04], row=1, col=1)
    fig.update_yaxes(showticklabels=False, row=2, col=1)
    T.plot(fig, 420)
    T.show(f'<div class="amb-note"><span class="amb-tag calc">Calc</span>{T.esc(m["trend"])}.</div>')

    if vol:
        T.section("Statistical price ranges", "if the next months are as volatile as the last year", "Not a forecast")
        rows, ranges = [], {}
        for label, d in (("1 month", 21), ("3 months", 63), ("6 months", 126)):
            r = Q.statistical_range(q["price"], vol, d)
            ranges[label] = r
            rows.append(f'<tr><td>{label}</td><td>{T.money(r.low68)} – {T.money(r.high68)}</td>'
                        f'<td>{T.money(r.low95)} – {T.money(r.high95)}</td></tr>')
        ctx["ranges"] = ranges
        T.show(f'<div class="amb-wrap"><table class="amb-table"><thead><tr><th>Horizon</th><th>68% of the time</th>'
               f'<th>95% of the time</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
               f'<div class="amb-note">Zero-drift lognormal band using {T.pct(vol, 0, signed=False)} annual volatility.</div>')
    dd = Q.drawdown_series(close.iloc[-252:])
    fig = go.Figure(go.Scatter(x=dd.index, y=dd.values * 100, mode="lines", line=dict(color=T.C["down"], width=1.5),
                               fill="tozeroy", fillcolor=T.rgba("down", .1), name="Drawdown"))
    fig.update_yaxes(ticksuffix="%")
    T.plot(fig, 220, "Drawdown from the previous high, 1 year")
    _tail_risk(sym, close, q, ctx)


def _tail_risk(sym, close, q, ctx):
    t95, t99 = Q.tail_risk(close, level=0.95), Q.tail_risk(close, level=0.99)
    if not t95:
        return
    T.section("Tail risk", f"daily returns, last {t95['days']} sessions", "Value at risk")
    T.show(T.kv([
        ("1-day VaR 95%", f'<span style="color:var(--down)">{T.pct(-t95["var"])}</span>', "loss not exceeded on 19 of 20 days"),
        ("Expected shortfall 95%", f'<span style="color:var(--down)">{T.pct(-t95["cvar"])}</span>', "average loss on the worst 1 in 20 days"),
        ("1-day VaR 99%", f'<span style="color:var(--down)">{T.pct(-t99["var"])}</span>',
         f"a normal model says {T.pct(-t99['var_normal'])}"),
        ("Worst day", T.pct(t95["worst"]), f"best {T.pct(t95['best'])}"),
        ("Skewness", f'{t95["skew"]:.2f}', "below 0: crashes bigger than rallies"),
        ("Excess kurtosis", f'{t95["kurt"]:.1f}', "above 0: fatter tails than normal"),
    ]))
    r = close.dropna().pct_change().dropna().iloc[-t95["days"]:] * 100
    sd = float(r.std())
    fig = go.Figure(go.Histogram(x=r, nbinsx=70, marker_color=T.rgba("acc", .55), name="Daily returns",
                                 hovertemplate="%{x:.1f}%: %{y} days<extra></extra>"))
    xs = [float(r.mean()) + sd * i / 15 for i in range(-60, 61)]
    bw = (r.max() - r.min()) / 70
    ys = [len(r) * bw * math.exp(-0.5 * ((x - r.mean()) / sd) ** 2) / (sd * math.sqrt(2 * math.pi)) for x in xs]
    fig.add_scatter(x=xs, y=ys, mode="lines", line=dict(color=T.C["text2"], width=1.4, dash="dot"), name="Normal curve")
    fig.add_vline(x=-t95["var"] * 100, line=dict(color=T.C["down"], width=1.2, dash="dash"),
                  annotation_text="VaR 95%", annotation_font_color=T.C["down"])
    fig.update_xaxes(ticksuffix="%")
    fig.update_layout(bargap=0.05, hovermode="closest")
    T.plot(fig, 260, "Daily returns vs a normal distribution")
    n_extreme, n_exp = t95["beyond3sd"], t95["expected3sd"]
    T.show(f'<div class="amb-note">Historical VaR uses the real distribution of daily moves instead of assuming a bell curve. '
           f'{T.esc(sym)} moved more than 3 standard deviations on {n_extreme} days; a normal distribution expects about '
           f'{n_exp:.1f}. That gap is why normal-based risk models understate crashes. In dollars, a 95% one-day VaR on '
           f'$10,000 is {T.money(10000 * t95["var"], 0)}.</div>')
    ctx["risk"] = (f"1-day VaR 95% {t95['var']:.1%}, expected shortfall {t95['cvar']:.1%}, skew {t95['skew']:.2f}, "
                   f"excess kurtosis {t95['kurt']:.1f}, {n_extreme} days beyond 3 sd vs {n_exp:.1f} expected")


