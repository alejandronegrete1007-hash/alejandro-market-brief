"""Valuation tab: cost of capital built step by step, a five-year DCF valued four ways
(levered / unlevered x perpetuity / exit multiple), bear-base-bull scenarios with probabilities,
peer-multiple values, football field and sensitivity."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import adr
import filings
import quant as Q
import sources as src
import theme as T
import valuation as V

ERP_DEFAULT = 5.0  # % : course guides put the US premium at 4.45% (Damodaran) to 5.5% (surveys)
ERP_MX_USD = 7.31  # % : seminar's dollar model for Mexico, US premium + Mexico's country risk premium
ERP_MX_MXN = 7.25  # % : seminar's peso model, Mexican market premium over the Bono M (7% to 7.5%)


def _slider(label, key, lo, hi, default, step, help_=None, fmt="%.1f%%"):
    """Percent slider that shows whole percents and returns a fraction."""
    default = float(np.clip(default, lo, hi))
    return st.slider(label, lo, hi, round(default / step) * step, step, key=key, help=help_, format=fmt) / 100


def multiples(sym, ctx):
    try:
        km = src.key_metrics(sym)
    except Exception:
        km = {}
    ctx["multiples"] = {k: v for k, v in km.items() if k not in ("hi52", "lo52")}
    T.section("Multiples", "trailing twelve months · Finnhub", "Relative value")
    T.show(T.kv([
        ("P/E", T.mult(km.get("pe")), "price / earnings"),
        ("Forward P/E", T.mult(km.get("fwd_pe")), "on expected earnings"),
        ("EV/EBITDA", T.mult(km.get("ev_ebitda")), ""),
        ("P/S", T.mult(km.get("ps")), "price / sales"),
        ("EV/FCF", T.mult(km.get("ev_fcf")), ""),
        ("Net margin", T.pct(km.get("net_margin"), 1, False, frac=False), ""),
        ("ROE", T.pct(km.get("roe"), 1, False, frac=False), ""),
        ("Revenue growth", T.pct(km.get("rev_growth"), 1, True, frac=False), "year over year"),
    ]))
    return km


def _margin_history(f) -> pd.Series:
    if f["ebitda"].empty:
        return pd.Series(dtype=float)
    rev = f["revenue"].reindex(f["ebitda"].index)
    return (f["ebitda"] / rev).dropna()


def basis(sym: str, f: dict, price: float, market: str) -> tuple[dict, dict]:
    """Currency and share basis of the model.

    The DCF runs in the currency of the filing, so cash flows and the discount rate match (pesos for most
    Mexican ADRs, at a peso rate). Other foreign currencies are converted to dollars at today's rate and use
    the dollar model. Per-share results are always in dollars per US-listed share: dividing pesos by
    (ADRs × pesos per dollar) gives dollars per ADR, so 'shares' below is that product."""
    notes = []
    cur = f["currency"]
    fx, fx_label = 1.0, ""
    if cur not in ("USD", "MXN"):
        rate, lbl = src.fx_per_usd(cur)
        f = filings.convert(f, 1 / rate, "USD")
        notes.append(f"Converted from {cur} to dollars at {lbl}; growth and margins are those of the {cur} statements.")
        cur = "USD"
    elif cur == "MXN":
        fx, fx_label = src.fx_per_usd("MXN")
    if f["taxonomy"] == "ifrs-full":
        try:
            prof = src.profile(sym)
            pc = prof.get("currency") or "USD"  # Finnhub may quote an ADR's market value in the home currency
            mcap_usd = prof["mcap"] / src.fx_per_usd(pc)[0] if prof.get("mcap") else None
        except Exception:
            mcap_usd = None
        ads, how = adr.ads_count(sym, f["share_candidates"], price, mcap_usd)
    else:
        ads, how = f["shares"], f["shares_source"]
    return f, {"cur": cur, "cs": f["cur_symbol"], "fx": fx, "fx_label": fx_label, "ads": ads, "ads_source": how,
               "shares": ads * fx, "mx": market == "MX", "notes": notes, "ratio": adr.RATIO.get(sym.upper())}


def render(sym, q, m, rf, rf_label, close, market, ctx):
    price = q["price"]
    ctx["filings"] = None
    try:
        if src.is_etf(sym):
            raise filings.FilingsError("This is an ETF (a basket of securities), so it has no cash flows of its own to "
                                       "discount. Use the chart, risk and research tabs instead.")
        with st.spinner("Reading the company's annual reports at the SEC..."):
            f = filings.build(src.sec_facts_full(sym))
        if not f["revenue0"] or f["ebitda_margin"] is None:
            raise filings.FilingsError("Revenue or operating income isn't tagged in the SEC data for this company.")
        f, b = basis(sym, f, price, market)
    except Exception as e:
        T.show(f'<div class="amb-empty">DCF not available for {T.esc(sym)}. {T.esc(str(e))}</div>')
        multiples(sym, ctx)
        return
    ctx["filings"] = f
    ctx["basis"] = b
    cs, cur = b["cs"], b["cur"]

    shares, debt, cash = b["shares"], f["debt"], f["cash"]
    mcap = price * shares
    ebitda0 = f["revenue0"] * f["ebitda_margin"]
    ev_mkt = mcap + debt - cash
    cur_mult = ev_mkt / ebitda0 if ebitda0 > 0 else None
    try:
        pm = src.peer_multiples(sym)
    except Exception:
        pm = {"tickers": []}
    k = f"{sym}_"

    # ---------------------------------------------------------------- cost of capital
    form = f["form"]
    peso = cur == "MXN"
    T.section("Cost of capital", f"CAPM for equity, the {form} for debt, market-value weights"
              + (" · in pesos" if peso else ""), "Discount rate")
    beta_raw, beta_vs = m["beta"], "vs S&P 500"
    if b["mx"]:
        # A Mexican company's premium is the Mexican market's, so its beta is measured against that market.
        ew = src.try_history("EWW")
        bm = Q.beta(close, ew["close"]) if ew is not None else None
        if bm is not None:
            beta_raw, beta_vs = bm, "vs Mexican market (EWW)"
    beta_adj = V.adjusted_beta(beta_raw)
    if peso:
        rf_m, rf_m_label = src.mx_bond_10y()
        rf_src = "Mexico 10Y Bono M (Banxico)"
        erp_d, erp_help = ERP_MX_MXN, ("Premium of the Mexican stock market over the Bono M. The seminar's peso model uses "
                                       "7% to 7.5%; it already includes Mexico's country risk.")
    elif b["mx"]:
        rf_m, rf_m_label, rf_src = rf, rf_label, "US 10Y Treasury (FRED)"
        erp_d, erp_help = ERP_MX_USD, ("This company reports in dollars, so the dollar model: the US premium plus Mexico's "
                                       "country risk premium, about 7.31% in the seminar's numbers.")
    else:
        rf_m, rf_m_label, rf_src = rf, rf_label, "US 10Y Treasury (FRED)"
        erp_d, erp_help = ERP_DEFAULT, ("Extra return investors demand for stocks over Treasuries. Damodaran (NYU) estimates "
                                        "about 4.45% for the US; valuation surveys use 4.5% to 5.5%.")
    c1, c2 = st.columns([1, 4], gap="large")
    with c1:
        erp = _slider("Equity risk premium", k + "erp", 3.0, 10.0, erp_d, 0.05, erp_help, "%.2f%%")
    beta_used = float(np.clip(beta_adj, 0.5, 2.5))
    ke0 = V.capm(rf_m, beta_used, erp)
    kd0 = float(np.clip((f["interest"] / debt) if (f["interest"] and debt) else rf_m + 0.015, rf_m + 0.005,
                        max(0.12, rf_m + 0.05)))
    tax_floor = 0.30 if b["mx"] else 0.21  # statutory rate when the effective one isn't meaningful
    tax0 = f["tax_rate"] if (f["tax_rate"] is not None and f["tax_rate"] >= 0.05) else tax_floor
    wacc0 = V.wacc(ke0, kd0, tax0, mcap, debt)
    we, wd = mcap / (mcap + debt), debt / (mcap + debt)
    with c2:
        T.show(T.kv([
            ("Risk-free rate", T.pct(rf_m, 2, False), rf_src),
            ("Beta", f"{beta_used:.2f}", (f"adjusted; raw {beta_raw:.2f} {beta_vs}, 2y weekly" + (", floored at 0.5" if beta_adj < 0.5 else ""))
             if beta_raw is not None else "no history: 1.0"),
            ("Cost of equity", T.pct(ke0, 2, False), f"{rf_m:.2%} + {beta_used:.2f} × {erp:.2%}"),
            ("Cost of debt", T.pct(kd0 * (1 - tax0), 2, False), f"{kd0:.2%} pre-tax × (1 − {tax0:.0%})"),
            ("Weights", f"{we:.0%} / {wd:.0%}", "equity / debt at market value"),
            ("WACC", T.pct(wacc0, 2, False), "weighted average" + (", in pesos" if peso else "")),
        ]))
    if peso:
        T.show('<div class="amb-note">This company reports in pesos, so the model stays in pesos: peso cash flows discounted '
               'at a peso rate (the 10-year Bono M plus beta × the Mexican market premium), as in the seminar\'s peso model. '
               'Only the final value is turned into dollars per ADR, at today\'s FIX. Mixing peso cash flows with a dollar '
               'rate would ignore that Mexican inflation runs above US inflation. Adjusted beta = 0.67 × measured beta + 0.33 '
               '(Blume).</div>')
    else:
        T.show('<div class="amb-note">Adjusted beta = 0.67 × measured beta + 0.33 (Blume), because betas drift toward 1 over '
               'time; it is the beta Bloomberg shows by default. The risk-free rate is the 10-year Treasury, to match the '
               'long life of the cash flows.' + (' This company reports in dollars, so it uses the dollar model with '
                                                  'Mexico\'s country risk inside the premium.' if b["mx"] else '') + '</div>')

    # ---------------------------------------------------------------- defaults
    g_hist = Q.cagr(f["revenue"]) if not f["revenue"].empty else None
    g0 = float(np.clip(g_hist if g_hist is not None else 0.06, -0.05, 0.15))
    m0 = f["ebitda_margin"]
    mh = _margin_history(f).iloc[-5:]
    m_avg = float(mh.mean()) if len(mh) >= 3 else None
    target0 = m_avg if (m_avg is not None and m_avg > 0) else (m0 if m0 > 0 else 0.10)
    nwc0 = f.get("nwc_pct")
    nwc0 = 0.10 if nwc0 is None else nwc0
    # Exit multiple: the lower of today's own EV/EBITDA and the peers' median, so the model never assumes the stock
    # gets re-rated upward, kept between 4x and 25x because by year 5 the business is assumed to be mature.
    peer_ev = (pm.get("ev_ebitda") or {}).get("median")
    cands = [(x, lbl) for x, lbl in (
        (cur_mult, f"today's own EV/EBITDA ({T.mult(cur_mult)})"),
        (peer_ev, f"median of {pm['ev_ebitda']['n']} peers ({T.mult(peer_ev)}: {', '.join(pm['tickers'][:5])})" if peer_ev else "")
    ) if x and x > 0]
    if cands:
        mult0, mult_src = min(cands, key=lambda c: c[0])
        others = [lbl for x, lbl in cands if lbl != mult_src]
        mult_src = f"the lower of {mult_src}" + (f" and {others[0]}" if others else "")
    else:
        mult0, mult_src = 12.0, "a market-average 12x (no multiple available)"
    mult0 = float(np.clip(mult0, 4.0, 25.0))

    T.section("Assumptions", f"defaults from the {form} (FY ending {f['fiscal_end']}), peers and market data", "Discounted cash flow")
    erp_tag = f"{erp:.4f}"  # rates that depend on the premium reset when it changes
    c = st.columns(5)
    with c[0]:
        tax = _slider("Tax rate", k + "tax", 0.0, 40.0, tax0 * 100, 0.5,
                      f"Default: effective tax rate in the last {form} ({tax_floor:.0%} if not meaningful).")
    with c[1]:
        g = _slider("Growth, yrs 1-5", k + "g", -10.0, 40.0, g0 * 100, 0.5,
                    f"Revenue growth per year; earnings follow at the chosen margin. Default: 5-year revenue CAGR "
                    f"({T.pct(g_hist, 1)}), capped at 15% because few companies sustain more for five years.")
    with c[2]:
        wacc = _slider("Discount rate (WACC)", k + "wacc" + erp_tag, 5.0, 22.0, wacc0 * 100, 0.1,
                       f"Default {wacc0:.1%}, built above. {rf_m_label}")
    with c[3]:
        tg = _slider("Perpetual growth", k + "tg", 0.0, 7.0 if peso else 4.0, 4.5 if peso else 2.5, 0.1,
                     ("Growth forever after year 5, in pesos: about Banxico's 3% inflation target plus 1.5% real growth. "
                      if peso else "Growth forever after year 5. ")
                     + "Keep it at or below long-run nominal GDP and below the risk-free rate.")
    with c[4]:
        mult = st.slider("EV/EBITDA exit multiple", 2.0, 40.0, float(np.clip(round(mult0 * 2) / 2, 2.0, 40.0)), 0.5,
                         key=k + "mult", help=f"Default: {mult_src}, kept between 4x and 25x. By year 5 the business is mature, so the default never assumes a re-rating.",
                         format="%.1fx")
    c = st.columns(5)
    with c[0]:
        ke = _slider("Cost of equity", k + "ke" + erp_tag, 5.0, 25.0, ke0 * 100, 0.1, "Discount rate for the levered DCF (CAPM above).")
    with c[1]:
        mt = _slider("EBITDA margin, yr 5", k + "mt", -20.0, 80.0, target0 * 100, 0.5,
                     f"Today {m0:.1%}; average of the last {len(mh)} years {T.pct(m_avg, 1, False)}. The default reverts to "
                     f"that average by year 5, because peak or trough margins rarely last.")
    with c[2]:
        capex = _slider("Capex, % revenue", k + "capex", 0.0, 50.0, (f["capex_pct"] or 0) * 100, 0.5,
                        "Default: last fiscal year. In the perpetuity year capex settles at most 15% above D&A.")
    with c[3]:
        da = _slider("D&A, % revenue", k + "da", 0.0, 40.0, (f["da_pct"] or 0) * 100, 0.5, "Default: last fiscal year.")
    with c[4]:
        nwc = _slider("Working capital, % of new revenue", k + "nwc", -20.0, 40.0, nwc0 * 100, 1.0,
                      f"Cash tied up in receivables + inventory − payables per extra unit of sales. Default: last {form} balance sheet.")
    if st.button("Reset to defaults", key=k + "reset"):
        for key_ in list(st.session_state.keys()):
            if isinstance(key_, str) and key_.startswith(k) and not key_.startswith(k + "sens") and not key_.startswith(k + "p_"):
                st.session_state.pop(key_, None)
        st.rerun()

    if wacc <= tg + 0.005 or ke <= tg + 0.005:
        st.error("Both discount rates must be clearly above the perpetual growth rate.")
        multiples(sym, ctx)
        return
    a = V.Inputs(revenue0=f["revenue0"], growth=g, margin0=m0, margin_target=mt, da_pct=da, capex_pct=capex, nwc_pct=nwc,
                 tax=tax, wacc=wacc, ke=ke, kd=kd0, tg=tg, exit_mult=mult, debt0=debt, cash0=cash, shares=shares)
    v = V.value(a)

    # ---------------------------------------------------------------- scenarios
    sc_in = V.scenario_inputs(a)
    sc_val = {}
    for name, x in sc_in.items():
        try:
            sc_val[name] = V.value(x)["average"]
        except ValueError:
            sc_val[name] = np.nan
    pc = st.columns([1, 1, 2], gap="medium")
    p_bear = pc[0].slider("Bear probability", 0, 60, 25, 5, key=k + "p_bear", format="%d%%")
    p_bull = pc[1].slider("Bull probability", 0, 60, 25, 5, key=k + "p_bull", format="%d%%")
    p_base = max(100 - p_bear - p_bull, 0)
    probs = {"Bear": p_bear, "Base": p_base, "Bull": p_bull}
    weighted = V.weighted({kk: vv for kk, vv in sc_val.items() if np.isfinite(vv)},
                          {kk: probs[kk] for kk in sc_val if np.isfinite(sc_val[kk])})
    pc[2].markdown(f"Base case gets the remaining **{p_base}%**. Bear and bull move growth ±5 pts, the year-5 margin "
                   f"±15%, the exit multiple ±20% and both discount rates ∓1 pt.")
    label, gap = V.verdict(weighted, price)
    implied = V.implied_growth(a, price)
    cls = {"Undervalued": "under", "Overvalued": "over"}.get(label, "fair")
    u, l_ = v["unlevered"], v["levered"]

    # ---------------------------------------------------------------- headline
    T.section("Market value vs intrinsic value", "probability-weighted value of the three scenarios", "Result")
    T.show(f"""
    <div class="amb-verdict {cls}">
      <div><div class="amb-eyebrow" style="margin-bottom:6px">DCF verdict</div><div class="big">{label}</div>
        <div class="amb-note" style="margin-top:6px">Intrinsic value is {T.pct(gap, 0)} vs the market price</div></div>
      <div class="nums">
        <div><div class="k">Intrinsic / share</div><div class="v">{T.money(weighted)}</div></div>
        <div><div class="k">Market price</div><div class="v">{T.money(price)}</div></div>
        <div><div class="k">Bear – bull</div><div class="v">{T.money(sc_val['Bear'])} – {T.money(sc_val['Bull'])}</div></div>
        <div><div class="k">Price implies</div><div class="v">{(T.pct(implied, 1) + ' growth') if implied is not None else '—'}</div></div>
      </div>
    </div>""")

    def vs(x):
        return f'<span style="color:var(--{T.tone(x / price - 1)})">{T.pct(x / price - 1, 0)}</span>' if T.is_num(x) else "—"

    srows = []
    for name in V.SCENARIOS:
        x = sc_in[name]
        srows.append(f'<tr class="{"hl" if name == "Base" else ""}"><td>{name}</td><td>{probs[name]}%</td><td>{T.pct(x.growth, 1)}</td>'
                     f'<td>{T.pct(x.margin_target, 1, False)}</td><td>{x.exit_mult:.1f}x</td><td>{T.pct(x.wacc, 1, False)}</td>'
                     f'<td>{T.money(sc_val[name])}</td><td>{vs(sc_val[name])}</td></tr>')
    srows.append(f'<tr class="sub"><td>Probability-weighted</td><td>100%</td><td></td><td></td><td></td><td></td>'
                 f'<td>{T.money(weighted)}</td><td>{vs(weighted)}</td></tr>')
    T.show('<div class="amb-wrap" style="margin-top:12px"><table class="amb-table"><thead><tr><th>Scenario</th><th>Probability</th>'
           f'<th>Growth</th><th>Margin yr 5</th><th>Exit</th><th>WACC</th><th>Value / {"ADR" if b["ratio"] and b["ratio"] != 1 else "share"}</th><th>vs price</th></tr></thead>'
           f'<tbody>{"".join(srows)}</tbody></table></div>')

    # ---------------------------------------------------------------- four methods (base case)
    T.section("Base case, four ways", "levered and unlevered, perpetuity and exit multiple", "Methods")
    rows = [
        ("Market", T.big(mcap, cs), T.big(ev_mkt, cs), T.money(price), "—"),
        ("Unlevered · perpetuity", T.big(u["perpetuity"]["equity"], cs), T.big(u["perpetuity"]["ev"], cs), T.money(u["perpetuity"]["per_share"]), vs(u["perpetuity"]["per_share"])),
        ("Unlevered · exit multiple", T.big(u["exit"]["equity"], cs), T.big(u["exit"]["ev"], cs), T.money(u["exit"]["per_share"]), vs(u["exit"]["per_share"])),
        ("Levered · perpetuity", T.big(l_["perpetuity"]["equity"], cs), "—", T.money(l_["perpetuity"]["per_share"]), vs(l_["perpetuity"]["per_share"])),
        ("Levered · exit multiple", T.big(l_["exit"]["equity"], cs), "—", T.money(l_["exit"]["per_share"]), vs(l_["exit"]["per_share"])),
        ("Average (base case)", "", "", T.money(v["average"]), vs(v["average"])),
    ]
    body = "".join(f'<tr class="{"sub" if i == 0 else "hl" if i == len(rows) - 1 else ""}"><td>{a_}</td><td>{b_}</td><td>{c_}</td>'
                   f'<td>{d_}</td><td>{e_}</td></tr>' for i, (a_, b_, c_, d_, e_) in enumerate(rows))
    per = "Per ADR (US$)" if b["ratio"] and b["ratio"] != 1 else "Per share"
    T.show(f'<div class="amb-wrap"><table class="amb-table"><thead><tr><th>Method</th><th>Equity value</th>'
           f'<th>Enterprise value</th><th>{per}</th><th>vs price</th></tr></thead><tbody>{body}</tbody></table></div>')
    T.show(T.kv([
        ("Net debt", T.big(debt - cash, cs), f"debt {T.big(debt, cs)} − cash {T.big(cash, cs)}"),
        ("EV/EBITDA today", T.mult(cur_mult), "market EV / last-year EBITDA"),
        ("Perpetuity implies", T.mult(v["implied_exit_mult"]), "exit EV/EBITDA"),
        ("Exit multiple implies", T.pct(v["implied_tg"], 1, False) if v["implied_tg"] is not None else "—", "perpetual growth"),
        ("Terminal value share", T.pct(u["perpetuity"]["tv_share"], 0, False), "of EV, perpetuity method"),
        (("ADRs" if b["ratio"] and b["ratio"] != 1 else "Shares"), f"{b['ads'] / 1e6:,.0f}M", b["ads_source"]),
    ]))
    if peso:
        T.show(f'<div class="amb-note">Values in the table are in pesos; per ADR = peso equity value ÷ ({b["ads"] / 1e6:,.0f}M ADRs '
               f'× {b["fx"]:.2f} pesos per dollar). {T.esc(b["fx_label"])}.</div>')
    T.show('<div class="amb-note"><b>Unlevered</b>: free cash flow to the firm (before debt payments) discounted at the WACC, '
           'minus net debt. <b>Levered</b>: free cash flow to shareholders (after interest and new borrowing) discounted at '
           'the cost of equity. <b>Perpetuity</b> values year 6 (normalized: growth, working capital and borrowing at the '
           'perpetual rate, capex near D&A) as a growing perpetuity; <b>exit multiple</b> sells the business at year 5 for '
           'EBITDA × multiple. When the four agree, the result is more robust.</div>')

    # ---------------------------------------------------------------- projection
    p = v["projection"]
    term = v["terminal"]
    T.section("5-year projection", f"{'pesos' if peso else 'US$'} millions · year 6 is the normalized perpetuity year", "Model")
    lines = [("Revenue", "revenue"), ("EBITDA", "ebitda"), ("EBITDA margin", "margin"), ("− D&A", "da"), ("EBIT", "ebit"),
             ("− Taxes", "taxes"), ("− Capex", "capex"), ("− Working capital", "dnwc"), ("FCFF (unlevered)", "fcff"),
             ("− Interest after tax", None), ("+ Net borrowing", "net_borrow"), ("FCFE (levered)", "fcfe")]
    head = "".join(f"<th>Year {y}</th>" for y in p.index) + "<th>Year 6</th>"
    trs = []
    for name, col in lines:
        if col == "margin":
            cells = "".join(f"<td>{x:.1%}</td>" for x in p[col]) + f"<td>{mt:.1%}</td>"
        elif col is None:
            cells = "".join(f"<td>{x * (1 - tax) / 1e6:,.0f}</td>" for x in p["interest"]) + f"<td>{term['interest'] * (1 - tax) / 1e6:,.0f}</td>"
        else:
            extra = term.get(col)
            cells = "".join(f"<td>{x / 1e6:,.0f}</td>" for x in p[col]) + (f"<td>{extra / 1e6:,.0f}</td>" if extra is not None else "<td></td>")
        cls_ = "hl" if col in ("fcff", "fcfe") else ("sub" if name.startswith(("−", "+")) else "")
        trs.append(f'<tr class="{cls_}"><td>{name}</td>{cells}</tr>')
    T.show(f'<div class="amb-wrap"><table class="amb-table"><thead><tr><th></th>{head}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>')
    if m0 <= 0:
        T.show(f'<div class="amb-note">This company lost money at the EBITDA level last year ({m0:.1%} margin). The value depends '
               f'almost entirely on the year-5 margin you set: try a few levels to see the range.</div>')

    # ---------------------------------------------------------------- peers' multiples
    try:
        km = src.key_metrics(sym)
    except Exception:
        km = {}
    comps = []
    for key_, nm in (("ev_ebitda", "Peers' EV/EBITDA"), ("pe", "Peers' P/E"), ("ps", "Peers' P/S")):
        d = pm.get(key_)
        if not d:
            continue
        if key_ == "ev_ebitda":
            if ebitda0 <= 0:
                continue
            conv = lambda x: (x * ebitda0 - (debt - cash)) / shares  # noqa: E731  (shares already include the FX)
        else:
            own = km.get(key_)
            if not own or own <= 0:
                continue
            conv = lambda x, own=own: price * x / own  # noqa: E731
        comps.append((nm, conv(d["q1"]), conv(d["median"]), conv(d["q3"]), d["n"]))

    # ---------------------------------------------------------------- football field + sensitivity
    a1, a2 = st.columns([1.3, 1], gap="large")
    with a1:
        T.section("Football field", "ranges vs today's price", "All methods")
        bars = []
        if len(close) > 200:
            bars.append(("52-week range", close.iloc[-252:].min(), close.iloc[-252:].max(), T.C["us"]))
        if m["vol"]:
            r = Q.statistical_range(price, m["vol"], 63)
            bars.append(("3-month stat. range", r.low95, r.high95, T.C["ai"]))
        for nm, lo, _, hi, _ in comps:
            bars.append((nm + " (25th–75th pct.)", min(lo, hi), max(lo, hi), T.C["mx"]))
        if all(np.isfinite(list(sc_val.values()))):
            bars.append(("DCF scenarios, bear – bull", sc_val["Bear"], sc_val["Bull"], T.C["acc"]))
        for nm, pick, field, delta in (
                ("Unlevered · perpetuity", lambda x: x["unlevered"]["perpetuity"]["per_share"], "tg", 0.005),
                ("Unlevered · exit", lambda x: x["unlevered"]["exit"]["per_share"], "exit_mult", 2.0),
                ("Levered · perpetuity", lambda x: x["levered"]["perpetuity"]["per_share"], "tg", 0.005),
                ("Levered · exit", lambda x: x["levered"]["exit"]["per_share"], "exit_mult", 2.0)):
            vals = []
            for dw in (-0.01, 0.01):
                for dc in (-delta, delta):
                    try:
                        vals.append(pick(V.value(replace(a, wacc=wacc + dw, ke=ke + dw, **{field: getattr(a, field) + dc}))))
                    except ValueError:
                        pass
            if vals:
                bars.append((nm, min(vals), max(vals), T.rgba("acc", .55)))
        fig = go.Figure()
        for lbl, lo, hi, colr in bars:
            fig.add_trace(go.Bar(y=[lbl], x=[hi - lo], base=[lo], orientation="h", marker=dict(color=colr),
                                 hovertemplate=f"{lbl}<br>${lo:,.2f} – ${hi:,.2f}<extra></extra>", showlegend=False))
        fig.add_vline(x=price, line=dict(color=T.C["text"], width=1.5, dash="dash"),
                      annotation_text=f"Price {T.money(price)}", annotation_font_color=T.C["text"])
        fig.add_vline(x=weighted, line=dict(color=T.C["acc"], width=1.5),
                      annotation_text=f"Weighted {T.money(weighted)}", annotation_position="bottom right",
                      annotation_font_color=T.C["acc"])
        fig.update_layout(bargap=0.4, hovermode="closest", margin=dict(l=8, r=16, t=30, b=8))
        fig.update_xaxes(tickprefix="$", gridcolor=T.C["line"])
        fig.update_yaxes(tickfont=dict(family="Inter Tight", color=T.C["text2"]), autorange="reversed")
        T.plot(fig, 380)
        T.show('<div class="amb-note">Peer bars apply the peers\' 25th to 75th percentile multiple to this company. DCF method '
               'bars move WACC (and cost of equity) ±1 pt and perpetual growth ±0.5 pt or the exit multiple ±2x.</div>')
    with a2:
        T.section("Sensitivity", "unlevered value per " + ("ADR, US$" if b["ratio"] and b["ratio"] != 1 else "share"), "What-if")
        sens_kind = st.segmented_control("Terminal", ["Perpetual growth", "Exit multiple"], default="Perpetual growth",
                                         key=k + "sens", label_visibility="collapsed")
        waccs = [wacc - 0.01, wacc - 0.005, wacc, wacc + 0.005, wacc + 0.01]
        if sens_kind == "Exit multiple":
            cols = [max(mult - 4, 1), mult - 2 if mult > 3 else mult, mult, mult + 2, mult + 4]
            tbl = V.grid(a, waccs, cols, "exit_mult", lambda x: x["unlevered"]["exit"]["per_share"])
            tbl.columns = [f"{c_:.1f}x" for c_ in tbl.columns]
        else:
            cols = [tg - 0.01, tg - 0.005, tg, tg + 0.005, tg + 0.01]
            tbl = V.grid(a, waccs, cols, "tg", lambda x: x["unlevered"]["perpetuity"]["per_share"])
            tbl.columns = [f"g {c_ * 100:.1f}%" for c_ in tbl.columns]
        tbl.index = [f"WACC {w * 100:.1f}%" for w in tbl.index]

        def shade(x):
            if not T.is_num(x):
                return ""
            al = min(abs(x / price - 1) / 0.5, 1) * 0.45 + 0.08
            return f"background-color: {T.rgba('up' if x >= price else 'down', round(al, 2))}; color: {T.C['text']}"
        st.dataframe(tbl.style.format("${:,.0f}").map(shade), width="stretch")
        T.show(f'<div class="amb-note">Green above today\'s price ({T.money(price)}), red below.</div>')

    _history_chart(f)
    with st.expander("Data notes"):
        T.show(T.kv([("Revenue, last FY", T.big(f["revenue0"], cs), f["fiscal_end"] or ""),
                     ("EBITDA margin, last FY", T.pct(m0, 1, False), "EBIT + D&A"),
                     ("Cost of debt (pre-tax)", T.pct(kd0, 2, False), "interest / debt"),
                     ("Steady-state capex", T.pct(V.steady_capex(a), 1, False), "of revenue, perpetuity year")]))
        for n in f["notes"] + b["notes"]:
            st.caption("• " + n)
        if f["taxonomy"] == "ifrs-full":
            st.caption("• Source: XBRL data of the 20-F at the SEC (IFRS). When the SEC's company facts haven't caught up "
                       "with the newest 20-F, its figures are read straight from the filing.")
        else:
            st.caption("• Debt is financial debt (notes, loans, finance leases); operating leases are left out. Free cash flow is "
                       "before stock-based compensation, which flatters companies that pay staff in shares.")
    multiples(sym, ctx)

    ctx["dcf"] = {"avg": v["average"], "weighted": weighted, "verdict": label, "gap": gap, "implied_g": implied,
                  "g": g, "wacc": wacc, "ke": ke, "tg": tg, "tax": tax, "mult": mult, "erp": erp, "beta_adj": beta_used,
                  "u_perp": u["perpetuity"]["per_share"], "u_exit": u["exit"]["per_share"],
                  "l_perp": l_["perpetuity"]["per_share"], "l_exit": l_["exit"]["per_share"],
                  "scenarios": sc_val, "probs": probs, "comps": comps, "margin_target": mt, "rf": rf_m,
                  "currency": cur, "form": form}


def _history_chart(f):
    T.section("Revenue, EBITDA and free cash flow", f"fiscal years · SEC {f['form']} · {f['currency']}", "History")
    fig = go.Figure()
    fig.add_bar(x=f["revenue"].index.year, y=f["revenue"].values / 1e9, name="Revenue", marker_color=T.C["line2"])
    if not f["ebitda"].empty:
        fig.add_bar(x=f["ebitda"].index.year, y=f["ebitda"].values / 1e9, name="EBITDA", marker_color=T.C["acc"])
    fig.add_bar(x=f["fcf"].index.year, y=f["fcf"].values / 1e9, name="Free cash flow",
                marker_color=[T.C["mx"] if x >= 0 else T.C["down"] for x in f["fcf"].values])
    fig.update_yaxes(ticksuffix="B", tickprefix=f["cur_symbol"].strip())
    fig.update_layout(barmode="group")
    T.plot(fig, 280)
