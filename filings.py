"""Pull the inputs a DCF needs out of SEC XBRL 'company facts'.

Annual figures come from 10-K filings: rows covering a full fiscal year
(about 365 days), one per fiscal year-end, keeping the most recently filed
version so restatements win. That respects fiscal years that don't end in
December (Micron ends in August, Dell in January).
"""
from __future__ import annotations

import pandas as pd

ANNUAL_FORMS = {"10-K", "10-K/A", "10-KT"}
PERIODIC_FORMS = ANNUAL_FORMS | {"10-Q", "10-Q/A"}

TAGS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "ocf": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
              "PaymentsForCapitalImprovements"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue",
             "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "st_investments": ["MarketableSecuritiesCurrent", "ShortTermInvestments",
                       "AvailableForSaleSecuritiesDebtSecuritiesCurrent"],
    "lt_investments": ["MarketableSecuritiesNoncurrent", "AvailableForSaleSecuritiesDebtSecuritiesNoncurrent"],
    "debt_total": ["LongTermDebt"],
    "debt_noncurrent": ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"],
    "debt_current": ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent", "DebtCurrent"],
    "short_borrowings": ["ShortTermBorrowings", "CommercialPaper"],
    "ebit": ["OperatingIncomeLoss"],
    "da": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
           "DepreciationAmortizationAndAccretionNet", "Depreciation"],
    "tax_expense": ["IncomeTaxExpenseBenefit"],
    "pretax": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
               "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
               "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic"],
    "gross_profit": ["GrossProfit"],
    "cogs": ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold"],
    "sbc": ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"],
    "interest": ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt",
                 "InterestAndDebtExpense", "InterestPaidNet"],
}


# Balance-sheet items (point in time), read at each fiscal year-end.
BALANCE = {
    "assets": ["Assets"],
    "assets_current": ["AssetsCurrent"],
    "liabilities_current": ["LiabilitiesCurrent"],
    "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "receivables": ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent"],
    "inventory": ["InventoryNet"],
    # Broadest operating payables first: accrued liabilities are part of operating working capital too.
    "payables": ["AccountsPayableCurrent", "AccountsPayableAndAccruedLiabilitiesCurrent", "AccountsPayableTradeCurrent"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue",
             "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "st_investments": ["MarketableSecuritiesCurrent", "ShortTermInvestments",
                       "AvailableForSaleSecuritiesDebtSecuritiesCurrent"],
    "lt_investments": ["MarketableSecuritiesNoncurrent", "AvailableForSaleSecuritiesDebtSecuritiesNoncurrent"],
    "debt_total": ["LongTermDebt"],
    "debt_noncurrent": ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"],
    "debt_current": ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent", "DebtCurrent"],
    "short_borrowings": ["ShortTermBorrowings", "CommercialPaper"],
}


class FilingsError(Exception):
    pass


def _gaap(facts: dict) -> dict:
    return facts.get("facts", {}).get("us-gaap", {})


def annual(facts: dict, tags: list[str], unit: str = "USD") -> pd.Series:
    """Fiscal-year values indexed by fiscal year-end date. First tag with data wins,
    later tags only fill years the first one doesn't cover."""
    gaap, combined = _gaap(facts), None
    for tag in tags:
        rows = []
        for r in gaap.get(tag, {}).get("units", {}).get(unit, []):
            if r.get("form") not in ANNUAL_FORMS or not r.get("start"):
                continue
            days = (pd.Timestamp(r["end"]) - pd.Timestamp(r["start"])).days
            if 340 <= days <= 380:
                rows.append(r)
        if not rows:
            continue
        df = pd.DataFrame(rows).sort_values("filed").drop_duplicates("end", keep="last")
        s = pd.Series(df["val"].astype(float).values, index=pd.to_datetime(df["end"])).sort_index()
        combined = s if combined is None else combined.combine_first(s)
    return combined if combined is not None else pd.Series(dtype=float)


def annual_instant(facts: dict, tags: list[str], unit: str = "USD") -> pd.Series:
    """Balance-sheet values reported in 10-Ks, indexed by the balance-sheet date."""
    gaap, combined = _gaap(facts), None
    for tag in tags:
        rows = [r for r in gaap.get(tag, {}).get("units", {}).get(unit, [])
                if r.get("form") in ANNUAL_FORMS and not r.get("start")]
        if not rows:
            continue
        df = pd.DataFrame(rows).sort_values("filed").drop_duplicates("end", keep="last")
        s = pd.Series(df["val"].astype(float).values, index=pd.to_datetime(df["end"])).sort_index()
        combined = s if combined is None else combined.combine_first(s)
    return combined if combined is not None else pd.Series(dtype=float)


def _at(series: pd.Series, dates: pd.DatetimeIndex) -> pd.Series:
    """Values on (or within a week of) each fiscal year-end."""
    if series.empty:
        return pd.Series(index=dates, dtype=float)
    return series.reindex(dates, method="nearest", tolerance=pd.Timedelta(days=7))


def balance_history(facts: dict, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """One row per fiscal year-end with the balance-sheet items the ratios need."""
    df = pd.DataFrame({k: _at(annual_instant(facts, tags), dates) for k, tags in BALANCE.items()}, index=dates)
    # Some filers tag only their notes as LongTermDebt and report finance leases inside the
    # current / non-current lines (Micron), so take whichever total is larger.
    parts = df["debt_noncurrent"].fillna(0) + df["debt_current"].fillna(0)
    df["debt"] = pd.concat([df["debt_total"].fillna(0), parts], axis=1).max(axis=1) + df["short_borrowings"].fillna(0)
    df["cash_all"] = df["cash"].fillna(0) + df["st_investments"].fillna(0) + df["lt_investments"].fillna(0)
    return df


def latest(facts: dict, tags: list[str], unit: str = "USD") -> dict | None:
    """Most recent balance-sheet value from a 10-K or 10-Q."""
    gaap, best = _gaap(facts), None
    for tag in tags:
        rows = [r for r in gaap.get(tag, {}).get("units", {}).get(unit, []) if r.get("form") in PERIODIC_FORMS]
        if rows:
            r = max(rows, key=lambda r: (r["end"], r.get("filed", "")))
            if best is None or r["end"] > best["end"]:
                best = {"val": float(r["val"]), "end": r["end"]}
    return best


def _recent(item: dict | None, ref: str | None, max_days: int = 400) -> dict | None:
    if not item or not ref:
        return item
    return item if (pd.Timestamp(ref) - pd.Timestamp(item["end"])).days <= max_days else None


def shares(facts: dict) -> dict | None:
    rows = facts.get("facts", {}).get("dei", {}).get("EntityCommonStockSharesOutstanding", {}).get("units", {}).get("shares", [])
    if rows:
        last = max(rows, key=lambda r: (r.get("filed", ""), r["end"]))
        same = [r for r in rows if r.get("accn") == last.get("accn") and r["end"] == last["end"]]  # share classes
        return {"val": float(sum(r["val"] for r in same)), "end": last["end"], "source": "cover of latest filing"}
    diluted = annual(facts, ["WeightedAverageNumberOfDilutedSharesOutstanding"], unit="shares")
    if not diluted.empty:
        return {"val": float(diluted.iloc[-1]), "end": diluted.index[-1].date().isoformat(), "source": "diluted average"}
    return None


def build(facts: dict) -> dict:
    if not _gaap(facts):
        raise FilingsError("This company doesn't report in US GAAP (foreign filers use IFRS on a 20-F), "
                           "so the automatic DCF isn't available.")
    notes = []
    rev, ni, ocf, capex = (annual(facts, TAGS[k]) for k in ("revenue", "net_income", "ocf", "capex"))
    if ocf.empty:
        raise FilingsError("Operating cash flow isn't in the SEC data, so free cash flow can't be computed.")
    if capex.empty:
        notes.append("Capex not found: free cash flow equals operating cash flow.")
    fcf = (ocf - capex.reindex(ocf.index).fillna(0.0)).dropna()

    cash = latest(facts, TAGS["cash"])
    ref = cash["end"] if cash else None
    sti = _recent(latest(facts, TAGS["st_investments"]), ref)
    lti = _recent(latest(facts, TAGS["lt_investments"]), ref)
    total = _recent(latest(facts, TAGS["debt_total"]), ref)
    split = [d for d in (_recent(latest(facts, TAGS["debt_noncurrent"]), ref),
                         _recent(latest(facts, TAGS["debt_current"]), ref)) if d]
    # Take the larger of the tagged total and current + non-current (some filers tag only notes as the total).
    parts = split if sum(d["val"] for d in split) > (total["val"] if total else 0) else ([total] if total else [])
    sb = _recent(latest(facts, TAGS["short_borrowings"]), ref)
    if sb:
        parts.append(sb)
    cash_total = sum(x["val"] for x in (cash, sti, lti) if x)
    if lti:
        notes.append(f"Cash includes {lti['val'] / 1e9:,.1f}B of long-term marketable securities (liquid bonds).")
    debt = sum(p["val"] for p in parts)
    if not cash:
        notes.append("Cash not found; assumed zero.")
    if not parts:
        notes.append("No debt found; assumed zero. Check the 10-K if that looks wrong.")
    sh = shares(facts)
    if not sh:
        raise FilingsError("Shares outstanding aren't in the SEC data.")

    ebit, da, tax_exp, pretax, interest = (annual(facts, TAGS[k]) for k in ("ebit", "da", "tax_expense", "pretax", "interest"))
    if ebit.empty and not pretax.empty:
        ebit = pretax.add(interest, fill_value=0)
        notes.append("Operating income not tagged; EBIT = pre-tax income + interest.")
    if da.empty:
        notes.append("D&A not found; assumed zero, so EBITDA equals EBIT.")

    def last(series):
        return float(series.iloc[-1]) if not series.empty else None

    def ratio(num, den, lo, hi):
        n, d = last(num), last(den)
        if n is None or not d:
            return None
        return float(min(max(n / d, lo), hi))

    rev0 = last(rev)
    gp, cogs, sbc = (annual(facts, TAGS[k]) for k in ("gross_profit", "cogs", "sbc"))
    if gp.empty and not cogs.empty:
        gp = rev.sub(cogs, fill_value=None).dropna()
    bal = balance_history(facts, rev.index) if not rev.empty else pd.DataFrame()
    nwc_pct = None
    if not bal.empty:
        lastb = bal.iloc[-1]
        if pd.notna(lastb.get("receivables")) or pd.notna(lastb.get("inventory")):
            if pd.isna(lastb.get("payables")):
                notes.append("Accounts payable not tagged, so working capital may be overstated.")
            nwc = (0 if pd.isna(lastb["receivables"]) else lastb["receivables"]) + \
                  (0 if pd.isna(lastb["inventory"]) else lastb["inventory"]) - \
                  (0 if pd.isna(lastb["payables"]) else lastb["payables"])
            if rev0:
                nwc_pct = float(min(max(nwc / rev0, -0.2), 0.4))
    ebitda = (ebit.add(da.reindex(ebit.index).fillna(0.0)) if not ebit.empty else pd.Series(dtype=float))
    tail = lambda s: s.iloc[-8:]  # noqa: E731
    return {
        "name": facts.get("entityName", ""),
        "revenue": tail(rev), "net_income": tail(ni), "ocf": tail(ocf), "capex": tail(capex), "fcf": tail(fcf),
        "ebit": tail(ebit), "ebitda": tail(ebitda), "da": tail(da),
        "revenue0": rev0, "fiscal_end": rev.index[-1].date().isoformat() if not rev.empty else None,
        "ebitda_margin": ratio(ebitda, rev, -1.0, 0.9),
        "ebitda_margin_3y": (float((ebitda.iloc[-3:] / rev.reindex(ebitda.index).iloc[-3:]).mean())
                             if len(ebitda) >= 3 and not rev.empty else None),
        "da_pct": ratio(da, rev, 0.0, 0.4) if not da.empty else 0.0,
        "capex_pct": ratio(capex, rev, 0.0, 0.6) if not capex.empty else 0.0,
        "tax_rate": ratio(tax_exp, pretax, 0.0, 0.35),
        "interest": last(interest),
        "cash": cash_total, "debt": debt, "net_debt": debt - cash_total, "balance_date": ref,
        "shares": sh["val"], "shares_source": sh["source"], "notes": notes,
        "gross_profit": tail(gp), "sbc": tail(sbc), "tax_expense": tail(tax_exp), "pretax": tail(pretax),
        "interest_hist": tail(interest), "balance": bal.iloc[-8:] if not bal.empty else bal,
        "nwc_pct": nwc_pct,
    }
