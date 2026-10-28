"""Financial statement analysis, as taught in the finance seminar: horizontal and vertical
analysis, liquidity / leverage / activity / profitability ratios, the DuPont decomposition,
earnings quality checks and Economic Value Added (EVA).

Pure pandas on the dict returned by filings.build(), so every ratio can be unit-tested.
Ratios that use balance-sheet items take the average of the opening and closing balance
when both are available, and the closing balance otherwise.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _avg(s: pd.Series) -> pd.Series:
    """Average of this year-end and last year-end; falls back to the year-end value."""
    return ((s + s.shift(1)) / 2).fillna(s)


def _div(a, b):
    a, b = pd.Series(a, dtype=float), pd.Series(b, dtype=float)
    return a.div(b.where(b != 0))


def table(f: dict) -> pd.DataFrame:
    """One column per fiscal year, one row per metric (fractions, or 'x' multiples / days)."""
    rev = f["revenue"].astype(float)
    idx = rev.index
    bal = f.get("balance")
    bal = bal.reindex(idx) if isinstance(bal, pd.DataFrame) and not bal.empty else pd.DataFrame(index=idx)

    def col(name):
        return bal[name] if name in bal else pd.Series(np.nan, index=idx)

    def inc(key):
        s = f.get(key)
        return s.reindex(idx).astype(float) if isinstance(s, pd.Series) and not s.empty else pd.Series(np.nan, index=idx)

    ni, ocf, ebit, ebitda, fcf, gp = (inc(k) for k in ("net_income", "ocf", "ebit", "ebitda", "fcf", "gross_profit"))
    interest, sbc = inc("interest_hist"), inc("sbc")
    assets, equity, debt, cash = col("assets"), col("equity"), col("debt"), col("cash_all")
    ca, cl, ar, inv, ap = (col(k) for k in ("assets_current", "liabilities_current", "receivables", "inventory", "payables"))
    cogs = rev - gp

    rows = {
        # horizontal analysis
        "Revenue growth": rev.pct_change(),
        "Net income growth": _div(ni - ni.shift(1), ni.shift(1).abs()),
        # vertical analysis (common size, % of revenue)
        "Gross margin": _div(gp, rev),
        "EBITDA margin": _div(ebitda, rev),
        "Operating (EBIT) margin": _div(ebit, rev),
        "Net margin": _div(ni, rev),
        "Free cash flow margin": _div(fcf, rev),
        "Stock comp, % revenue": _div(sbc, rev),
        # liquidity
        "Current ratio": _div(ca, cl),
        "Quick ratio": _div(col("cash").fillna(0) + col("st_investments").fillna(0) + ar.fillna(0), cl),
        # leverage
        "Debt / equity": _div(debt, equity),
        "Net debt / EBITDA": _div(debt.fillna(0) - cash.fillna(0), ebitda),
        "Interest coverage (EBIT / interest)": _div(ebit, interest),
        # activity
        "Asset turnover": _div(rev, _avg(assets)),
        "Days sales outstanding": _div(_avg(ar), rev) * 365,
        "Days inventory": _div(_avg(inv), cogs) * 365,
        # profitability and DuPont
        "ROA": _div(ni, _avg(assets)),
        "ROE": _div(ni, _avg(equity)),
        "DuPont · net margin": _div(ni, rev),
        "DuPont · asset turnover": _div(rev, _avg(assets)),
        "DuPont · equity multiplier": _div(_avg(assets), _avg(equity)),
        # earnings quality
        "Cash conversion (CFO / net income)": _div(ocf, ni),
        "Accruals ratio ((NI − CFO) / assets)": _div(ni - ocf, _avg(assets)),
        "Receivables growth − revenue growth": ar.pct_change() - rev.pct_change(),
        "Year-end receivables, days of sales": _div(ar, rev) * 365,
    }
    out = pd.DataFrame(rows).T
    out.columns = [f"FY{d.year}" for d in idx]
    return out


KIND = {  # how each row is displayed
    "Current ratio": "x", "Quick ratio": "x", "Debt / equity": "x", "Net debt / EBITDA": "x",
    "Interest coverage (EBIT / interest)": "x", "Asset turnover": "x", "DuPont · asset turnover": "x",
    "DuPont · equity multiplier": "x", "Cash conversion (CFO / net income)": "x",
    "Days sales outstanding": "days", "Days inventory": "days", "Year-end receivables, days of sales": "days",
}

GROUPS = [
    ("Growth (horizontal analysis)", ["Revenue growth", "Net income growth"]),
    ("Margins (vertical analysis, % of revenue)", ["Gross margin", "EBITDA margin", "Operating (EBIT) margin", "Net margin",
                                                   "Free cash flow margin", "Stock comp, % revenue"]),
    ("Liquidity", ["Current ratio", "Quick ratio"]),
    ("Leverage", ["Debt / equity", "Net debt / EBITDA", "Interest coverage (EBIT / interest)"]),
    ("Activity", ["Asset turnover", "Days sales outstanding", "Days inventory"]),
    ("Profitability", ["ROA", "ROE"]),
    ("DuPont: ROE = margin × turnover × leverage", ["DuPont · net margin", "DuPont · asset turnover", "DuPont · equity multiplier"]),
    ("Earnings quality", ["Cash conversion (CFO / net income)", "Accruals ratio ((NI − CFO) / assets)",
                          "Receivables growth − revenue growth", "Year-end receivables, days of sales"]),
]


def eva(ebit: float, tax: float, wacc: float, capital: float) -> dict:
    """EVA = NOPAT − WACC × capital employed, with NOPAT = EBIT × (1 − tax).
    Capital employed = interest-bearing debt + equity (total assets − non-interest-bearing current liabilities)."""
    nopat = ebit * (1 - tax)
    charge = wacc * capital
    return {"nopat": nopat, "capital": capital, "charge": charge, "eva": nopat - charge,
            "roic": nopat / capital if capital else None, "spread": (nopat / capital - wacc) if capital else None}


def eva_history(f: dict, tax: float, wacc: float) -> pd.DataFrame:
    """EVA for each fiscal year, on average capital employed (debt + equity)."""
    idx = f["revenue"].index
    bal = f.get("balance")
    if not isinstance(bal, pd.DataFrame) or bal.empty or "equity" not in bal:
        return pd.DataFrame()
    bal = bal.reindex(idx)
    capital = _avg(bal["debt"].fillna(0) + bal["equity"])
    ebit = f["ebit"].reindex(idx).astype(float) if not f["ebit"].empty else pd.Series(np.nan, index=idx)
    rows = []
    for d in idx:
        if pd.isna(ebit.get(d)) or pd.isna(capital.get(d)) or capital.get(d) <= 0:
            continue
        e = eva(float(ebit[d]), tax, wacc, float(capital[d]))
        rows.append({"year": d.year, **e})
    return pd.DataFrame(rows).set_index("year") if rows else pd.DataFrame()


def flags(t: pd.DataFrame) -> list[tuple[str, str]]:
    """Plain-language checks on the latest year: ('ok' | 'watch', message)."""
    if t.empty:
        return []
    last = t.iloc[:, -1]
    out = []

    def v(name):
        x = last.get(name)
        return None if x is None or pd.isna(x) else float(x)

    cc = v("Cash conversion (CFO / net income)")
    if cc is not None:
        out.append(("ok", f"Profits are backed by cash: operating cash flow is {cc:.1f}x net income.") if cc >= 0.9 else
                   ("watch", f"Operating cash flow is only {cc:.1f}x net income: check what is not turning into cash."))
    d_now = v("Year-end receivables, days of sales")
    d_before = t.iloc[:, -2].get("Year-end receivables, days of sales") if t.shape[1] >= 2 else None
    if d_now is not None and d_before is not None and not pd.isna(d_before):
        if d_now > d_before * 1.15 and d_now - d_before > 10:
            out.append(("watch", f"Year-end receivables rose to {d_now:.0f} days of sales from {d_before:.0f}: check whether sales "
                                 "are being booked early (a strong last quarter can also explain it)."))
        else:
            out.append(("ok", f"Receivables are in line with sales ({d_now:.0f} days at year-end, {d_before:.0f} the year before)."))
    ic = v("Interest coverage (EBIT / interest)")
    if ic is not None:
        out.append(("ok", f"Interest is covered {ic:.1f}x by operating profit.") if ic >= 4 else
                   ("watch", f"Interest coverage of {ic:.1f}x is thin (below 2x is a serious concern)."))
    cr = v("Current ratio")
    if cr is not None:
        out.append(("ok", f"Current ratio of {cr:.2f}x covers short-term obligations.") if cr >= 1 else
                   ("watch", f"Current ratio of {cr:.2f}x: short-term liabilities exceed short-term assets."))
    sb = v("Stock comp, % revenue")
    if sb is not None and sb > 0.05:
        out.append(("watch", f"Stock compensation is {sb:.0%} of revenue; free cash flow before it overstates owner earnings."))
    return out
