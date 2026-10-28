"""Outlook tab: where the price could go, from 4,000 simulated paths built from the stock's own daily moves."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import quant as Q
import theme as T

HORIZONS = [("1 month", 21), ("3 months", 63), ("6 months", 126)]


@st.cache_data(ttl=6 * 3600, show_spinner=False, max_entries=30)
def _paths(sym: str, close: pd.Series, drift: float) -> np.ndarray:
    return Q.simulate(close, horizon=126, n=4000, annual_drift=drift)


def render(sym: str, close: pd.Series, q: dict, ctx: dict):
    price = q["price"]
    T.section("Where the price could go", "simulation from the stock's real daily moves · next 6 months", "Projection")
    r1y = Q.period_return(close, 365)
    trend = float(np.clip(r1y, -0.30, 0.30)) if r1y is not None else 0.0
    choice = st.segmented_control(
        "Drift", ["Neutral", "Market average", "Recent trend"], default="Neutral", key=f"drift_{sym}",
        help="Neutral: no upward or downward bias, only volatility. Market average: +8% a year, roughly the long-run "
             f"return of stocks. Recent trend: last year's return, capped at ±30% ({trend:+.0%} here).")
    drift = {"Neutral": 0.0, "Market average": 0.08, "Recent trend": trend}.get(choice or "Neutral", 0.0)
    try:
        paths = _paths(sym, close, drift)
    except ValueError as e:
        T.show(f'<div class="amb-empty">{T.esc(str(e))}</div>')
        return
    f = Q.fan(paths)
    future = pd.bdate_range(close.index[-1] + pd.Timedelta(days=1), periods=len(f))
    hist = close.iloc[-126:]
    hi52, lo52 = close.iloc[-252:].max(), close.iloc[-252:].min()
    dcf = (ctx.get("dcf") or {}).get("avg")

    fig = go.Figure()
    fig.add_scatter(x=hist.index, y=hist.values, mode="lines", line=dict(color=T.C["text"], width=1.8), name="Price")
    x = [hist.index[-1]] + list(future)

    def band(lo, hi, color, name):
        fig.add_scatter(x=x, y=[price] + list(f[hi]), mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip")
        fig.add_scatter(x=x, y=[price] + list(f[lo]), mode="lines", line=dict(width=0), fill="tonexty",
                        fillcolor=color, name=name, hoverinfo="skip")
    band(5, 95, "rgba(232,176,75,.12)", "9 in 10 paths")
    band(25, 75, "rgba(232,176,75,.28)", "Half of the paths")
    fig.add_scatter(x=x, y=[price] + list(f[50]), mode="lines", line=dict(color=T.C["gold"], width=1.6, dash="dot"),
                    name="Middle path", hovertemplate="$%{y:,.2f}<extra>Median</extra>")
    levels = [(hi52, "52-week high", T.C["up"]), (lo52, "52-week low", T.C["down"])]
    if dcf and dcf > 0:
        levels.append((dcf, "DCF value", T.C["mx"]))
    for lvl, name, col in levels:
        fig.add_hline(y=lvl, line=dict(color=col, width=1, dash="dash"), annotation_text=f"{name} {T.money(lvl)}",
                      annotation_font=dict(color=col, size=11),
                      annotation_position="bottom right" if name == "DCF value" else "top left")
    lo_y = min(hist.min(), f[5].min(), dcf or np.inf) * 0.95
    hi_y = max(hist.max(), f[95].max(), (dcf or 0)) * 1.05
    fig.update_yaxes(range=[lo_y, hi_y], tickprefix="$")
    fig.update_layout(hovermode="x unified")
    T.plot(fig, 420)

    rows = "".join(
        f"<tr><td>{lbl}</td><td>{T.money(f[5][d - 1])}</td><td>{T.money(f[25][d - 1])}</td>"
        f"<td style='color:var(--gold)'>{T.money(f[50][d - 1])}</td><td>{T.money(f[75][d - 1])}</td><td>{T.money(f[95][d - 1])}</td></tr>"
        for lbl, d in HORIZONS)
    T.show(f'<div class="amb-wrap"><table class="amb-table"><thead><tr><th>Horizon</th><th>Bad (5%)</th><th>Weak (25%)</th>'
           f'<th>Middle</th><th>Good (75%)</th><th>Great (95%)</th></tr></thead><tbody>{rows}</tbody></table></div>')

    p3, p6 = Q.prob_end_above(paths, price, 63), Q.prob_end_above(paths, price, 126)
    crash = Q.prob_touch(paths, price * 0.8, above=False)
    reach_hi = Q.prob_touch(paths, hi52, above=True) if hi52 > price * 1.001 else 1.0
    items = [("Ends higher, 3 months", T.pct(p3, 0, False), "share of paths above today's price"),
             ("Ends higher, 6 months", T.pct(p6, 0, False), ""),
             ("Falls 20% at some point", T.pct(crash, 0, False), "within 6 months"),
             ("Revisits 52-week high", T.pct(reach_hi, 0, False), f"{T.money(hi52)} within 6 months")]
    reach_dcf = None
    if dcf and dcf > 0:
        reach_dcf = Q.prob_touch(paths, dcf, above=dcf > price)
        items.append(("Touches DCF value", T.pct(reach_dcf, 0, False), f"{T.money(dcf)} within 6 months"))
    T.show(T.kv(items))
    T.show(f'<div class="amb-note"><span class="amb-tag calc">Calc</span>4,000 paths, each day replaying a random real daily move '
           f'from the last two years, re-centred to a {drift:+.0%} yearly drift. That keeps the fat tails real stocks have, but '
           'assumes the next six months look like the last two years. These are the odds of a statistical model, not a '
           'forecast or a target.</div>')

    # ---- technical levels
    T.section("Key price levels", "distance from today's price", "Technicals")
    s50, s200 = Q.sma(close, 50).iloc[-1], Q.sma(close, 200).iloc[-1]
    m3 = close.iloc[-63:]
    lv = [("52-week high", hi52), ("3-month high", m3.max()), ("50-day average", s50), ("200-day average", s200),
          ("3-month low", m3.min()), ("52-week low", lo52)]
    T.show(T.kv([(n, T.money(v), f"{T.pct(v / price - 1, 1)} from here") for n, v in lv if T.is_num(v)]))
    ctx["outlook"] = (f"Simulation ({choice or 'Neutral'} drift {drift:+.0%}/yr): 6-month price range 5%-95% "
                      f"{f[5].iloc[-1]:.2f}-{f[95].iloc[-1]:.2f}, median {f[50].iloc[-1]:.2f}; probability of ending higher in "
                      f"6 months {p6:.0%}; probability of a 20% drop at some point {crash:.0%}"
                      + (f"; probability of touching the DCF value {reach_dcf:.0%}" if reach_dcf is not None else ""))
