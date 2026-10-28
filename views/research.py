"""Research note tab: the whole analysis of one stock condensed into a one-page note, as an analyst
would present it to an investment committee. Numbers come from the other tabs; the written thesis
comes from Gemini; the call (Buy / Hold / Sell) is yours to save and track."""
from __future__ import annotations

import datetime as dt
import html
import re

import streamlit as st

import ai
import sources as src
import state
import theme as T
from views.common import name_of

CONSENSUS = [(4.5, "Strong Buy", "up"), (3.5, "Buy", "up"), (2.5, "Hold", "flat"), (1.5, "Sell", "down"), (0, "Strong Sell", "down")]
LEAN = {"Buy": "up", "Hold": "flat", "Sell": "down"}
_LEAD = re.compile(r"^\s*(\d+[.)]|[-•*])\s*")


def consensus(sym, ctx):
    try:
        recs = src.recommendations(sym)
    except Exception:
        recs = []
    T.section("Wall Street consensus", "Finnhub analyst recommendation trends", "What the experts say")
    if not recs:
        T.show('<div class="amb-empty">No analyst ratings available for this ticker.</div>')
        return
    r = recs[0]
    keys = [("strongBuy", "Strong Buy", "#3F8F69"), ("buy", "Buy", T.C["up"]), ("hold", "Hold", T.C["text2"]),
            ("sell", "Sell", "#E89A8E"), ("strongSell", "Strong Sell", T.C["down"])]
    counts = [int(r.get(k_) or 0) for k_, _, _ in keys]
    n = sum(counts)
    if not n:
        T.show('<div class="amb-empty">No analyst ratings available for this ticker.</div>')
        return
    score = sum(c_ * w for c_, w in zip(counts, (5, 4, 3, 2, 1))) / n
    lbl, tone = next((lb, tn) for th, lb, tn in CONSENSUS if score >= th)
    bars = "".join(f'<i style="width:{c_ / n * 100:.1f}%;background:{col}" title="{nm}: {c_}"></i>'
                   for c_, (_, nm, col) in zip(counts, keys) if c_)
    legend = " · ".join(f"{nm} {c_}" for c_, (_, nm, _) in zip(counts, keys))
    trend = ""
    if len(recs) >= 4:
        old = recs[3]
        on = sum(int(old.get(k_) or 0) for k_, _, _ in keys)
        if on:
            os_ = sum(int(old.get(k_) or 0) * w for (k_, _, _), w in zip(keys, (5, 4, 3, 2, 1))) / on
            d = score - os_
            trend = f"{'more bullish' if d > 0.05 else 'more bearish' if d < -0.05 else 'unchanged'} vs {old.get('period', '')[:7]}"
    ctx["consensus"] = f"{lbl} (score {score:.2f}/5 from {n} analysts: {legend}; {trend or 'no trend data'})"
    ctx["consensus_label"] = lbl
    T.show(f"""
    <div class="amb-take">
      <div style="display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap">
        <div><div class="amb-eyebrow" style="margin-bottom:6px">{n} analysts · {r.get('period', '')[:7]}</div>
          <div style="font-family:var(--display);font-size:1.6rem;font-weight:500;color:var(--{tone if tone != 'flat' else 'text'})">{lbl}</div></div>
        <div style="color:var(--text2);font-size:.85rem">{score:.2f} / 5 {('· ' + trend) if trend else ''}</div>
      </div>
      <div class="amb-bars">{bars}</div>
      <div class="amb-note" style="margin-top:0">{legend}</div>
    </div>""")
    T.show('<div class="amb-note">Ratings from the brokerage analysts that cover the stock, aggregated monthly by Finnhub. '
           'Price targets are not in the free plan.</div>')


def facts(ctx) -> str:
    """Everything the app computed, as plain lines for the model."""
    q, m, p = ctx["q"], ctx["m"], ctx["prof"]
    lines = [f"Company: {name_of(ctx['sym'])} ({ctx['sym']}), industry: {p['industry'] or 'n/a'}, "
             f"{'Mexican company, NYSE-listed ADR' if ctx['market'] == 'MX' else 'US-listed'}",
             f"Price: {q['price']:.2f} ({q['pct']:+.2f}% today)",
             f"YTD return: {T.pct(m['ytd'])}; 1-year: {T.pct(m['r1y'])}; annualized volatility: {T.pct(m['vol'], 1, False)}; "
             f"1-year max drawdown: {T.pct(m['mdd'])}; beta: {m['beta'] if m['beta'] is None else round(m['beta'], 2)}; "
             f"Sharpe: {m['sharpe'] if m['sharpe'] is None else round(m['sharpe'], 2)}",
             f"Trend: {m['trend']}"]
    if ctx.get("risk"):
        lines.append(f"Tail risk: {ctx['risk']}")
    km = ctx.get("multiples") or {}
    if km:
        lines.append("Multiples: " + ", ".join(f"{k_}={v_:.2f}" for k_, v_ in km.items() if v_ is not None))
    d = ctx.get("dcf")
    if d:
        sc = d["scenarios"]
        lines.append(f"Cost of capital: WACC {d['wacc']:.1%}, cost of equity {d['ke']:.1%} (CAPM, adjusted beta {d['beta_adj']:.2f}, "
                     f"equity risk premium {d['erp']:.2%}).")
        lines.append(f"DCF base case (growth {d['g']:.1%} for 5 years, year-5 EBITDA margin {d['margin_target']:.1%}, perpetual growth "
                     f"{d['tg']:.1%}, exit {d['mult']:.1f}x EBITDA): unlevered perpetuity {d['u_perp']:.2f}, unlevered exit "
                     f"{d['u_exit']:.2f}, levered perpetuity {d['l_perp']:.2f}, levered exit {d['l_exit']:.2f}, average {d['avg']:.2f}.")
        lines.append(f"Scenarios: bear {sc['Bear']:.2f} ({d['probs']['Bear']}%), base {sc['Base']:.2f} ({d['probs']['Base']}%), "
                     f"bull {sc['Bull']:.2f} ({d['probs']['Bull']}%); probability-weighted {d['weighted']:.2f} -> {d['verdict']} "
                     f"({d['gap']:+.0%} vs price). Reverse DCF: price implies "
                     f"{('%.1f%%' % (d['implied_g'] * 100)) if d['implied_g'] is not None else 'n/a'} annual growth for 5 years.")
        if d.get("comps"):
            lines.append("Value at peers' median multiples: " + "; ".join(f"{nm} {mid:.2f} (n={n})" for nm, _, mid, _, n in d["comps"]))
    else:
        lines.append("DCF: not available for this security.")
    if ctx.get("fin_summary"):
        lines.append(f"Latest fiscal year: {ctx['fin_summary']}")
    if ctx.get("eva"):
        lines.append(f"Economic value added: {ctx['eva']}")
    if ctx.get("fin_flags"):
        lines.append(f"Health checks: {ctx['fin_flags']}")
    lines.append(f"Analyst consensus: {ctx.get('consensus') or 'not available'}")
    for k_, lbl in (("outlook", "Price simulation"), ("vs_market", "Versus the market"),
                    ("vs_sector", "Versus its sector"), ("vs_peers", "Relative valuation")):
        if ctx.get(k_):
            lines.append(f"{lbl}: {ctx[k_]}")
    if ctx.get("er"):
        lines.append(f"Next earnings date: {ctx['er']['date']} {ctx['er']['when']}")
    return "\n".join(lines)


def _bullets(items) -> str:
    """List items without any numbering or bullet the model added itself (the list already numbers them)."""
    return "".join(f"<li>{T.esc(_LEAD.sub('', str(x)))}</li>" for x in (items or []))


def _note_html(sym: str, ctx: dict, t: dict, call: str, day: str) -> str:
    """A standalone, printable copy of the note (open it in a browser and print to PDF)."""
    d = ctx.get("dcf") or {}
    q = ctx["q"]
    e = html.escape
    rows = ""
    if d:
        for nm in ("Bear", "Base", "Bull"):
            rows += f"<tr><td>{nm}</td><td>{d['probs'][nm]}%</td><td>${d['scenarios'][nm]:,.2f}</td></tr>"
        rows += f"<tr><th>Probability-weighted</th><th></th><th>${d['weighted']:,.2f}</th></tr>"
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{e(sym)} research note</title>
<style>body{{font:15px/1.6 'Inter Tight',Arial,sans-serif;color:#1d2026;max-width:760px;margin:40px auto;padding:0 24px}}
h1,h2{{font-family:Spectral,Georgia,serif;font-weight:500}}h1{{font-size:30px;margin:0}}h2{{font-size:19px;margin:26px 0 6px;border-bottom:1px solid #d9dce1}}
.meta{{color:#666;font-size:13px}}.call{{font:500 22px Spectral,Georgia,serif;margin:14px 0}}table{{border-collapse:collapse;width:100%}}
td,th{{padding:6px 8px;border-bottom:1px solid #e3e5e8;text-align:left;font-variant-numeric:tabular-nums}}</style></head><body>
<div class="meta">Alejandro Market Brief · research note · {e(day)}</div>
<h1>{e(name_of(sym))} ({e(sym)})</h1>
<div class="meta">Price ${q['price']:,.2f} · consensus {e(ctx.get('consensus_label') or 'n/a')}</div>
<div class="call">Call: {e(call)} · {e(t.get('conviction', ''))} conviction</div>
<p><b>{e(t.get('one_liner', ''))}</b></p>
<h2>Thesis</h2><ol>{_bullets(t.get('thesis'))}</ol>
<h2>Where we differ</h2><p>{e(t.get('variant', ''))}</p>
<h2>Valuation</h2><p>{e(t.get('valuation', ''))}</p><table>{rows}</table>
<h2>Quality</h2><p>{e(t.get('quality', ''))}</p>
<h2>Scenarios</h2><p><b>Bull.</b> {e(t.get('bull', ''))}</p><p><b>Base.</b> {e(t.get('base', ''))}</p><p><b>Bear.</b> {e(t.get('bear', ''))}</p>
<h2>Catalysts</h2><ul>{_bullets(t.get('catalysts'))}</ul>
<h2>Risks</h2><ul>{_bullets(t.get('risks'))}</ul>
<h2>What to monitor</h2><ul>{_bullets(t.get('monitor'))}</ul>
<h2>What would change the call</h2><p>{e(t.get('changes_mind', ''))}</p>
<p><b>{e(t.get('bottom_line', ''))}</b></p>
<p class="meta">Built from public data (SEC filings, Finnhub, Twelve Data, FRED) with the analyst's own DCF assumptions; the
written sections were drafted by a language model from those numbers and reviewed by the analyst. Not investment advice.</p>
</body></html>"""


def render(sym: str, ctx: dict):
    consensus(sym, ctx)
    d = ctx.get("dcf")
    q = ctx["q"]

    T.section("Research note", "every tab of this analysis on one page", "Investment view")
    cards = [("Price", T.money(q["price"]), f"{T.pct(ctx['m']['ytd'])} this year")]
    if d:
        cards += [("Intrinsic value", T.money(d["weighted"]), f"probability-weighted · {T.pct(d['gap'], 0)} vs price"),
                  ("Bear – bull", f"{T.money(d['scenarios']['Bear'], 0)} – {T.money(d['scenarios']['Bull'], 0)}", "DCF scenarios"),
                  ("Price implies", T.pct(d["implied_g"], 1) if d["implied_g"] is not None else "—", "revenue growth, 5 years")]
    e_ = ctx.get("eva_d")
    if e_:
        cards.append(("ROIC vs WACC", f"{e_['roic']:.0%} vs {e_['wacc']:.0%}",
                      f"EVA {T.big(e_['eva'])} · {'creates' if e_['eva'] > 0 else 'destroys'} value"))
    cards.append(("Consensus", ctx.get("consensus_label") or "—", "Wall Street analysts"))
    T.show(T.kv(cards))

    key = f"note_{sym}"
    if not (st.button("Write the research note", type="primary", key=f"btn_{key}") or st.session_state.get(key)):
        T.show('<div class="amb-empty">The note pulls together the valuation (with the assumptions you set), the financial '
               'analysis, risk, the comparison with peers and the analyst consensus, and writes the thesis, scenarios, '
               'risks and catalysts. You then make the call and can save it to track how it does against the S&P 500.</div>')
        return
    news = ctx.get("news") or []
    day = dt.date.today().isoformat()
    try:
        with st.spinner("Writing the note from the numbers on this page..."):
            t = ai.research_note(sym, facts(ctx),
                                 tuple(f"{n_['source']} | {n_['time']:%b %d} | {n_['title']} — {n_['summary'][:200]}"
                                       for n_ in news[:10] if n_.get("time")), day)
        st.session_state[key] = True
    except Exception as e:
        st.info(f"The written note isn't available right now ({e}). The numbers above still stand.")
        return

    lean = t.get("lean") if t.get("lean") in LEAN else "Hold"
    tone = LEAN[lean]
    col = {"up": "var(--up)", "down": "var(--down)", "flat": "var(--text)"}[tone]
    T.show(f"""
    <div class="amb-note-card">
      <div class="amb-note-head">
        <div><div class="amb-eyebrow">Model view · {T.esc(t.get('conviction', 'Low'))} conviction</div>
          <div class="call" style="color:{col}">{lean}</div></div>
        <p class="one">{T.esc(t.get('one_liner', ''))}</p>
      </div>
      <div class="amb-note-body">
        <div><h4>Thesis</h4><ol>{_bullets(t.get('thesis'))}</ol></div>
        <div><h4>Where this view differs</h4><p>{T.esc(t.get('variant', ''))}</p>
             <h4>Valuation</h4><p>{T.esc(t.get('valuation', ''))}</p>
             <h4>Quality</h4><p>{T.esc(t.get('quality', ''))}</p></div>
      </div>
    </div>""")
    st.write("")
    sc = [("Bull case", t.get("bull"), "up"), ("Base case", t.get("base"), "flat"), ("Bear case", t.get("bear"), "down")]
    T.show('<div class="amb-grid g3 stack">' + "".join(
        f'<div class="amb-story"><div class="top"><span class="amb-pill {c_}">{k_}</span></div>'
        f'<div class="row">{T.esc(v_ or "")}</div></div>' for k_, v_, c_ in sc) + "</div>")
    st.write("")
    lists = [("Catalysts", t.get("catalysts")), ("Risks", t.get("risks")), ("What to monitor", t.get("monitor"))]
    T.show('<div class="amb-grid g3 stack">' + "".join(
        f'<div class="amb-take"><div class="h">{k_}</div><ul class="amb-ul">{_bullets(v_)}</ul></div>' for k_, v_ in lists) + "</div>")
    T.show(f'<div class="amb-take" style="margin-top:12px"><div class="h">Why {lean.lower()}</div><p>{T.esc(t.get("lean_why", ""))}</p>'
           f'<p style="margin-top:8px"><b style="color:var(--text)">What would change it:</b> {T.esc(t.get("changes_mind", ""))}</p></div>')
    T.show(f'<div class="amb-lead" style="margin-top:20px">{T.esc(t.get("bottom_line", ""))}</div>')

    # ---- your call
    T.section("Your call", "save it and the Portfolio page tracks it against the S&P 500", "Track record")
    c1, c2, c3 = st.columns([1.2, 1, 1], gap="medium")
    with c1:
        call = st.segmented_control("Call", ["Buy", "Hold", "Sell"], default=lean, key=f"call_{sym}")
    with c2:
        if st.button("Save this call", key=f"save_{sym}", width="stretch"):
            spy = src.try_quote("SPY")
            state.save_call({"sym": sym, "date": day, "price": round(q["price"], 4), "spy": round(spy["price"], 4) if spy else None,
                             "lean": call or lean, "value": round(d["weighted"], 4) if d else None,
                             "conviction": t.get("conviction")})
            st.toast(f"Saved: {call or lean} {sym} at {T.money(q['price'])}")
    with c3:
        st.download_button("Download note", _note_html(sym, ctx, t, call or lean, day), file_name=f"{sym}_research_note_{day}.html",
                           mime="text/html", key=f"dl_{sym}", width="stretch")
    T.show('<div class="amb-note"><span class="amb-tag ai">AI</span>The written sections are drafted by a language model only '
           'from the numbers on this page; check them before relying on them. The call is yours. Not investment advice. '
           'The download opens in any browser; print it to PDF to share.</div>')
