"""Financials tab: statement analysis from the 10-K or 20-F (horizontal and vertical analysis, ratios,
DuPont, earnings quality) and Economic Value Added against the WACC set in Valuation."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

import fundamentals as F
import theme as T


def _fmt(name: str, x) -> str:
    if x is None or pd.isna(x):
        return "—"
    kind = F.KIND.get(name)
    if kind == "x":
        return f"{x:.2f}x"
    if kind == "days":
        return f"{x:.0f}"
    return T.pct(x, 1, signed=name.endswith(("growth", "growth − revenue growth")))


def render(sym: str, ctx: dict):
    f = ctx.get("filings")
    if not f:
        T.show('<div class="amb-empty">Statement analysis reads the annual reports companies file with the SEC: the 10-K of US '
               'companies and the 20-F of foreign ones such as the Mexican ADRs. ETFs have no statements of their own, and '
               'a few companies don\'t publish XBRL data. See the Valuation tab for the reason.</div>')
        return
    cs = f["cur_symbol"]
    t = F.table(f).iloc[:, -5:]
    d = ctx.get("dcf") or {}
    wacc, tax = d.get("wacc"), d.get("tax")

    # ---- health checks
    T.section("Health checks", "latest fiscal year", "Quality")
    checks = F.flags(t)
    if checks:
        T.show('<div class="amb-checks">' + "".join(
            f'<div class="amb-check {k}"><i></i><span>{T.esc(msg)}</span></div>' for k, msg in checks) + "</div>")

    # ---- EVA
    if wacc and tax is not None:
        h = F.eva_history(f, tax, wacc)
        if not h.empty:
            last = h.iloc[-1]
            T.section("Economic value added", f"NOPAT − WACC × capital employed · WACC {wacc:.1%} from Valuation", "Value creation")
            T.show(T.kv([
                ("NOPAT", T.big(last["nopat"], cs), f"EBIT × (1 − {tax:.0%}), FY{h.index[-1]}"),
                ("Capital employed", T.big(last["capital"], cs), "debt + equity, average of the year"),
                ("ROIC", T.pct(last["roic"], 1, False), "NOPAT / capital employed"),
                ("Spread", f'<span style="color:var(--{T.tone(last["spread"])})">{T.pct(last["spread"], 1)}</span>', "ROIC − WACC"),
                ("EVA", f'<span style="color:var(--{T.tone(last["eva"])})">{T.big(last["eva"], cs)}</span>',
                 "creates value" if last["eva"] > 0 else "destroys value"),
            ]))
            fig = go.Figure()
            fig.add_bar(x=h.index.astype(str), y=h["eva"] / 1e9, name="EVA",
                        marker_color=[T.C["up"] if x >= 0 else T.C["down"] for x in h["eva"]], yaxis="y")
            fig.add_scatter(x=h.index.astype(str), y=h["roic"] * 100, name="ROIC", mode="lines+markers",
                            line=dict(color=T.C["acc"], width=2), yaxis="y2")
            fig.add_scatter(x=h.index.astype(str), y=[wacc * 100] * len(h), name="WACC", mode="lines",
                            line=dict(color=T.C["text2"], width=1.2, dash="dash"), yaxis="y2")
            fig.update_layout(yaxis=dict(title=None, tickprefix=cs.strip(), ticksuffix="B"),
                              yaxis2=dict(overlaying="y", side="right", ticksuffix="%", tickformat=".0f", showgrid=False,
                                          tickfont=dict(color=T.C["muted"])))
            T.plot(fig, 300)
            ctx["eva_d"] = {"roic": last["roic"], "wacc": wacc, "spread": last["spread"], "eva": last["eva"], "cs": cs}
            ctx["eva"] = (f"FY{h.index[-1]}: ROIC {last['roic']:.1%} vs WACC {wacc:.1%} (spread {last['spread']:+.1%}); "
                          f"EVA {f['currency']} {last['eva'] / 1e9:+.2f}B")
            T.show('<div class="amb-note">A company creates value only when its return on capital beats what that capital costs. '
                   'Past years use today\'s WACC, so read the trend rather than each year\'s exact figure. Capital employed '
                   '= interest-bearing debt + equity (total assets minus non-interest-bearing current liabilities).</div>')

    # ---- statement analysis
    T.section("Statement analysis", f"fiscal years · SEC {f['form']}" + (" · IFRS" if f["taxonomy"] == "ifrs-full" else ""), "Ratios")
    head = "".join(f"<th>{c}</th>" for c in t.columns)
    body = ""
    for group, names in F.GROUPS:
        body += f'<tr class="grp"><td colspan="{len(t.columns) + 1}">{T.esc(group)}</td></tr>'
        for n in names:
            if n not in t.index:
                continue
            body += f"<tr><td>{T.esc(n.replace('DuPont · ', ''))}</td>" + "".join(f"<td>{_fmt(n, x)}</td>" for x in t.loc[n]) + "</tr>"
    T.show(f'<div class="amb-wrap"><table class="amb-table fin"><thead><tr><th></th>{head}</tr></thead><tbody>{body}</tbody></table></div>')
    T.show('<div class="amb-note">Balance-sheet ratios use the average of the opening and closing balance. Horizontal analysis '
           'compares each year with the one before; vertical analysis expresses each line as a share of revenue. '
           'DuPont splits ROE into margin × asset turnover × equity multiplier, so you can see whether returns come from '
           'pricing power, efficiency or debt.</div>')
    ctx["fin_flags"] = "; ".join(msg for _, msg in checks)
    last = t.iloc[:, -1]
    ctx["fin_summary"] = ", ".join(f"{n} {_fmt(n, last.get(n))}" for n in (
        "Revenue growth", "Operating (EBIT) margin", "Free cash flow margin", "ROE", "Debt / equity",
        "Interest coverage (EBIT / interest)", "Cash conversion (CFO / net income)") if n in last.index)
