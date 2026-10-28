"""Compare tab: the stock against the market, its sector, and its competitors."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import mexico
import quant as Q
import sources as src
import state
import theme as T
from views.common import name_of

LINE = T.SERIES
WINDOWS = ["YTD", "6M", "1Y", "2Y"]


def _hist(sym: str) -> pd.Series | None:
    h = src.try_history(sym)
    return h["close"] if h is not None else None


def _line_chart(df: pd.DataFrame, title: str):
    fig = go.Figure()
    for i, c in enumerate(df.columns):
        fig.add_scatter(x=df.index, y=df[c].values, mode="lines", name=c,
                        line=dict(color=LINE[i % len(LINE)], width=2.4 if i == 0 else 1.6),
                        hovertemplate=f"{c}: %{{y:.1f}}<extra></extra>")
    fig.add_hline(y=100, line=dict(color=T.C["line2"], width=1))
    T.plot(fig, 330, title)


def _ret_cell(x):
    return f'<span style="color:var(--{T.tone(x)})">{T.pct(x, 1)}</span>'


def render(sym: str, close: pd.Series, prof: dict, rf: float, market: str, ctx: dict):
    win = st.segmented_control("Window", WINDOWS, default="1Y", key=f"cmp_win_{sym}", label_visibility="collapsed") or "1Y"
    start = Q.window_start(close.index[-1], win)

    # ------------------------------------------------------------ 1. market
    T.section("Against the market", "all lines start at 100", "Benchmark")
    with st.spinner("Loading benchmark prices..."):
        spy = _hist("SPY")
        eww = _hist("EWW") if market == "MX" else None
    series = {sym: close, "S&P 500 (SPY)": spy}
    if eww is not None:
        series["Mexico (EWW)"] = eww
    df = Q.aligned(series)
    if len(df) < 30:
        T.show('<div class="amb-empty">Not enough shared price history to compare.</div>')
        return
    _line_chart(Q.rebased(df, start), f"{sym} vs the market · {win}")
    bench_name = "Mexico (EWW)" if eww is not None else "S&P 500 (SPY)"
    rs, rm = Q.window_return(df[sym], start), Q.window_return(df["S&P 500 (SPY)"], start)
    rx = Q.window_return(df["Mexico (EWW)"], start) if eww is not None else None
    b = Q.beta(df[sym], df[bench_name])
    a = Q.alpha(df[sym], df[bench_name], rf)
    corr = Q.correlation(df[sym], df[bench_name])
    up, dn = Q.capture(df[sym], df[bench_name])
    items = [(f"{sym} return", _ret_cell(rs), win), ("S&P 500 return", _ret_cell(rm), win)]
    if rx is not None:
        items.append(("Mexico (EWW) return", _ret_cell(rx), win))
    items += [("Beat the market by", _ret_cell((rs or 0) - ((rx if rx is not None else rm) or 0)), f"vs {bench_name}, in % points"),
              ("Beta", f"{b:.2f}" if b is not None else "—", "1.0 = moves like the market"),
              ("Alpha (1 year)", _ret_cell(a) if a is not None else "—", "return beyond what beta explains"),
              ("Correlation", f"{corr:.2f}" if corr is not None else "—", "1 = same direction every week"),
              ("Up / down capture", f"{T.pct(up, 0, False)} / {T.pct(dn, 0, False)}" if up is not None and dn is not None else "—",
               "share of the market's up / down weeks it catches")]
    T.show(T.kv(items))
    T.show('<div class="amb-note"><span class="amb-tag calc">Calc</span>Up capture above 100% and down capture below 100% is the '
           'ideal: more of the gains, less of the losses. Beta, correlation and capture use 2 years of weekly returns.</div>')
    ctx["vs_market"] = (f"{win}: {sym} {T.pct(rs)} vs S&P 500 {T.pct(rm)}"
                        + (f" and Mexico EWW {T.pct(rx)}" if rx is not None else "")
                        + f"; beta {b if b is None else round(b, 2)}, alpha {T.pct(a)}, correlation {corr if corr is None else round(corr, 2)}")

    # ------------------------------------------------------------ 2. sector
    T.section("Against its sector", "is it the stock, or the whole industry?", "Sector")
    default = "EWW" if market == "MX" else src.sector_etf(prof.get("industry", ""))
    choices = list(dict.fromkeys([default] + src.SECTOR_CHOICES + (["EWW"] if market == "MX" else [])))
    etf = st.selectbox("Sector ETF", choices, index=0, key=f"cmp_sector_{sym}",
                       format_func=lambda e: f"{e} · {src.ETFS.get(e, e)}",
                       help=f"Picked from the company's industry ({prof.get('industry') or 'n/a'}). Change it if a better fit exists.")
    with st.spinner("Loading sector prices..."):
        sec = _hist(etf)
    if sec is not None:
        d2 = Q.aligned({sym: close, f"{etf} · {src.ETFS.get(etf, etf)}": sec, "S&P 500 (SPY)": spy})
        _line_chart(Q.rebased(d2, start), f"{sym} vs its sector · {win}")
        rsec = Q.window_return(d2.iloc[:, 1], start)
        if None not in (rs, rsec, rm):
            parts = Q.decompose(rs, rsec, rm)
            total = abs(parts["market"]) + abs(parts["sector"]) + abs(parts["stock"]) or 1
            colors = {"market": T.C["us"], "sector": T.C["gold"], "stock": T.C["mx"]}
            bars = "".join(f'<i style="width:{abs(v) / total * 100:.1f}%;background:{colors[k]};opacity:{1 if v >= 0 else .45}"></i>'
                           for k, v in parts.items())
            T.show(f"""
            <div class="amb-take">
              <div class="h">Where the {T.pct(rs, 0)} came from ({win})</div>
              <div class="amb-bars">{bars}</div>
              <p><b style="color:var(--us)">Market</b> {T.pct(parts['market'], 1)} ·
                 <b style="color:var(--gold)">Sector over market</b> {T.pct(parts['sector'], 1)} ·
                 <b style="color:var(--mx)">{T.esc(sym)} over its sector</b> {T.pct(parts['stock'], 1)}</p>
            </div>""")
            T.show('<div class="amb-note">A simple split of the return in percentage points. Faded segments are negative. '
                   f'If most of it is the sector, {T.esc(sym)} is riding its industry; if most is the stock, it is company-specific.</div>')
            ctx["vs_sector"] = (f"{win}: sector {etf} {T.pct(rsec)}; decomposition market {T.pct(parts['market'])}, "
                                f"sector over market {T.pct(parts['sector'])}, stock over sector {T.pct(parts['stock'])}")
    else:
        T.show('<div class="amb-empty">Sector prices unavailable right now (free plan limit). Try again in a minute.</div>')

    # ------------------------------------------------------------ 3. peers
    T.section("Against its competitors", "comparable companies · Finnhub", "Comps")
    if market == "MX":
        suggested = [s for s in mexico.UNIVERSE if s != sym]
    else:
        try:
            suggested = src.peers(sym)
        except Exception:
            suggested = []
    sel = f"cmp_sel_{sym}"
    ss = st.session_state
    if sel not in ss:
        ss[sel] = suggested[:3]

    def _add_peer(t: str):
        if t != sym and t not in ss[sel] and len(ss[sel]) < 5:
            ss[sel] = ss[sel] + [t]

    def _pill_add(k: str):
        v = ss.get(k)
        if v:
            _add_peer(v)
        ss[k] = None

    def _pill_remove(k: str):
        v = ss.get(k)
        if v:
            ss[sel] = [t for t in ss[sel] if t != v]
        ss[k] = None

    picked = list(ss[sel])
    if picked:
        st.pills("Comparing with · tap to remove", picked, selection_mode="single", key=f"cmp_rm_{sym}",
                 on_change=_pill_remove, args=(f"cmp_rm_{sym}",), format_func=lambda t: f"✕  {t}")
    ideas = [t for t in dict.fromkeys(suggested[:10] + [x for x in state.all_symbols() if x != sym]) if t not in picked][:12]
    if ideas and len(picked) < 5:
        st.pills("Suggestions · tap to add", ideas, selection_mode="single", key=f"cmp_sug_{sym}",
                 on_change=_pill_add, args=(f"cmp_sug_{sym}",), format_func=lambda t: f"+  {t}")
    q = st.text_input("Search a competitor by name or ticker", key=f"cmp_q_{sym}",
                      placeholder="e.g. Samsung, Xiaomi, Sony, HP…")
    if q:
        try:
            res = [r for r in src.search(q) if r["symbol"] != sym]
        except Exception:
            res = []
        t_ = q.upper().strip()
        if not res and state.TICKER.match(t_) and t_ != sym:
            res = [{"symbol": t_, "name": "add by ticker"}]
        if not res:
            st.caption("No US-traded listing found for that name. Companies listed only abroad (Seoul, Hong Kong, "
                       "Tokyo…) aren't in the free data plans. If you know its US over-the-counter ticker, type it.")
        for r in res[:6]:
            c1, c2 = st.columns([5, 1])
            otc = len(r["symbol"]) == 5 and r["symbol"][-1] in "FY"
            c1.markdown(f"**{r['symbol']}** · {r['name']}" + (" · *OTC (over-the-counter)*" if otc else ""))
            c2.button("Add", key=f"cmp_add_{sym}_{r['symbol']}", on_click=_add_peer, args=(r["symbol"],), width="stretch")
    group = [sym] + picked
    rows = []
    with st.spinner("Loading competitor metrics..."):
        src.prefetch([c for s in group for c in ((src.try_quote, s), (src.key_metrics, s), (src.recommendations, s),
                                                 (src.profile, s))])
        for s in group:
            q = src.try_quote(s)
            try:
                km = src.key_metrics(s)
            except Exception:
                km = {}
            try:
                rec = src.recommendations(s)
                r0 = rec[0] if rec else {}
                n = sum(int(r0.get(k) or 0) for k in ("strongBuy", "buy", "hold", "sell", "strongSell"))
                score = (sum(int(r0.get(k) or 0) * w for k, w in (("strongBuy", 5), ("buy", 4), ("hold", 3), ("sell", 2), ("strongSell", 1))) / n) if n else None
            except Exception:
                score = None
            pr = src.profile(s)
            rows.append({"Ticker": s, "Price": q["price"] if q else None,
                         "Mkt cap": (pr["mcap"] or None) if pr.get("currency", "USD") == "USD" else None,
                         "YTD": km.get("ytd"), "1Y": km.get("r52"), "P/E": km.get("pe"), "Fwd P/E": km.get("fwd_pe"),
                         "EV/EBITDA": km.get("ev_ebitda"), "P/S": km.get("ps"), "Net margin": km.get("net_margin"),
                         "Rev. growth": km.get("rev_growth"), "ROE": km.get("roe"), "Analysts": score})
    comp = pd.DataFrame(rows).set_index("Ticker")
    if not picked:
        T.show('<div class="amb-empty">Pick or search at least one competitor to build the comparison table.</div>')
        return
    no_data = [t for t in picked if comp.loc[t, ["Price", "P/E", "EV/EBITDA", "P/S"]].isna().all()]
    peers_only = comp.drop(index=sym) if len(comp) > 1 else comp
    med = peers_only.median(numeric_only=True)

    cheaper_is_better = {"P/E", "Fwd P/E", "EV/EBITDA", "P/S"}
    higher_is_better = {"YTD", "1Y", "Net margin", "Rev. growth", "ROE", "Analysts"}
    fmt = {"Price": lambda v: T.money(v), "Mkt cap": lambda v: T.big(v), "YTD": lambda v: T.pct(v, 0, frac=False),
           "1Y": lambda v: T.pct(v, 0, frac=False), "P/E": T.mult, "Fwd P/E": T.mult, "EV/EBITDA": T.mult, "P/S": T.mult,
           "Net margin": lambda v: T.pct(v, 1, False, frac=False), "Rev. growth": lambda v: T.pct(v, 0, frac=False),
           "ROE": lambda v: T.pct(v, 0, False, frac=False), "Analysts": lambda v: f"{v:.1f}/5" if T.is_num(v) else "—"}

    def cell(col, v, is_main):
        txt = fmt[col](v) if T.is_num(v) else "—"
        style = ""
        if is_main and T.is_num(v) and T.is_num(med.get(col)) and med.get(col) and abs(v / med[col] - 1) > 0.02:
            better = (v < med[col]) if col in cheaper_is_better else (v > med[col]) if col in higher_is_better else None
            if better is not None and not (col in cheaper_is_better and v <= 0):
                style = f' style="color:var(--{"up" if better else "down"});font-weight:600"'
        return f"<td{style}>{txt}</td>"

    cols = list(fmt)
    head = "".join(f"<th>{c}</th>" for c in cols)
    body = ""
    for t, r in comp.iterrows():
        main = t == sym
        body += (f'<tr class="{"hl" if main else ""}"><td><span{T.go_attr("t:" + t) if not main else ""} '
                 f'style="cursor:{"pointer" if not main else "default"}">{T.esc(t)}</span></td>'
                 + "".join(cell(c, r[c], main) for c in cols) + "</tr>")
    body += '<tr class="sub"><td>Peer median</td>' + "".join(
        f"<td>{fmt[c](med[c]) if T.is_num(med.get(c)) else '—'}</td>" for c in cols) + "</tr>"
    from views.common import click
    click(f'<div class="amb-wrap"><table class="amb-table"><thead><tr><th>Company</th>{head}</tr></thead>'
          f'<tbody>{body}</tbody></table></div>', f"comps_{sym}")

    # relative valuation summary
    msgs = []
    for col, nm in (("Fwd P/E", "forward P/E"), ("EV/EBITDA", "EV/EBITDA"), ("P/S", "price-to-sales")):
        v, m_ = comp.loc[sym, col], med.get(col)
        if T.is_num(v) and T.is_num(m_) and v > 0 and m_ > 0:
            prem = v / m_ - 1
            msgs.append(f"in line on {nm}" if abs(prem) < 0.02 else f"at a {abs(prem):.0%} {'premium' if prem > 0 else 'discount'} on {nm}")
    if msgs:
        T.show(f'<div class="amb-take"><div class="h">Relative value</div><p>{T.esc(sym)} trades '
               f'{"; ".join(msgs)} vs the median of the peers selected. Green cells beat the peer median '
               f'(cheaper multiple, or higher growth, margin, return or rating); red ones lag it.</p></div>')
        ctx["vs_peers"] = f"vs peers {', '.join(picked)}: " + "; ".join(msgs)
    if no_data:
        T.show(f'<div class="amb-note" style="color:var(--gold)">No free data for {T.esc(", ".join(no_data))}. Usually this means the '
               'company trades over-the-counter or only on a foreign exchange, which the free plans do not cover.</div>')
    T.show('<div class="amb-note">Multiples are trailing twelve months unless marked forward. "Analysts" is the consensus score '
           '(5 = all strong buy, 1 = all strong sell). Click a competitor to open its analysis.</div>')

    if st.toggle("Show competitors' price performance", key=f"cmp_peerchart_{sym}",
                 help="Loads price history for each competitor (free plan: 8 requests per minute, so it can take a moment)."):
        with st.spinner("Loading competitor prices..."):
            ser = {sym: close}
            for p in picked:
                h = _hist(p)
                if h is not None:
                    ser[p] = h
        d3 = Q.aligned(ser)
        if len(d3) > 30:
            _line_chart(Q.rebased(d3, start), f"{sym} vs competitors · {win}")
