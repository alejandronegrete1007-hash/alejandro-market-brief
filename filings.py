"""Pull the inputs a DCF needs out of SEC XBRL 'company facts'.

Annual figures come from annual reports: the 10-K of US filers (US GAAP) and the 20-F of foreign filers
that report in IFRS, such as the Mexican ADRs. Rows covering a full fiscal year (about 365 days), one per
fiscal year-end, keeping the most recently filed version so restatements win. That respects fiscal years
that don't end in December (Micron ends in August, Dell in January).

IFRS filers report in their own currency (pesos for most Mexican companies). Figures stay in that
currency; the valuation converts only the final value per share. When a 20-F also shows the latest year
translated into dollars "for convenience", that translation is ignored.
"""
from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET

import pandas as pd

ANNUAL_FORMS = {"10-K", "10-K/A", "10-KT", "20-F", "20-F/A", "40-F", "40-F/A"}
PERIODIC_FORMS = ANNUAL_FORMS | {"10-Q", "10-Q/A", "6-K", "6-K/A"}

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


# The same items in the IFRS taxonomy (ifrs-full), as the 20-F filers tag them.
IFRS_TAGS = {
    "revenue": ["Revenue", "RevenueFromContractsWithCustomers"],
    "net_income": ["ProfitLossAttributableToOwnersOfParent", "ProfitLoss"],
    "ocf": ["CashFlowsFromUsedInOperatingActivities", "CashFlowsFromUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", "PurchaseOfPropertyPlantAndEquipment"],
    # Airports and other concessions invest through intangible assets, so their purchases count as capex too.
    "capex_intangibles": ["PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities", "PurchaseOfIntangibleAssets"],
    "cash": ["CashAndCashEquivalents"],
    "st_investments": ["CurrentInvestments", "ShorttermDepositsNotClassifiedAsCashEquivalents"],
    "lt_investments": [],
    "debt_total": ["Borrowings"],
    "debt_noncurrent": ["NoncurrentPortionOfNoncurrentBorrowings", "LongtermBorrowings"],
    "debt_current": ["CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings"],
    "short_borrowings": [],
    "leases": ["LeaseLiabilities"],
    "leases_parts": ["NoncurrentLeaseLiabilities", "CurrentLeaseLiabilities"],
    "ebit": ["ProfitLossFromOperatingActivities"],
    "da": ["DepreciationAndAmortisationExpense",
           "DepreciationAmortisationAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss",
           "AdjustmentsForDepreciationAndAmortisationExpense", "DepreciationExpense", "AdjustmentsForDepreciationExpense"],
    "tax_expense": ["IncomeTaxExpenseContinuingOperations"],
    "pretax": ["ProfitLossBeforeTax"],
    "gross_profit": ["GrossProfit"],
    "cogs": ["CostOfSales"],
    "sbc": ["ExpenseFromSharebasedPaymentTransactionsWithEmployees", "ExpenseFromSharebasedPaymentTransactions"],
    "interest": ["InterestExpense", "InterestExpenseOnBorrowings", "FinanceCosts"],
}
IFRS_BALANCE = {
    "assets": ["Assets"],
    "assets_current": ["CurrentAssets"],
    "liabilities_current": ["CurrentLiabilities"],
    "equity": ["EquityAttributableToOwnersOfParent", "Equity"],
    "receivables": ["TradeAndOtherCurrentReceivables", "CurrentTradeReceivables"],
    "inventory": ["Inventories"],
    "payables": ["TradeAndOtherCurrentPayables", "TradeAndOtherCurrentPayablesToTradeSuppliers", "CurrentTradePayables"],
    "cash": ["CashAndCashEquivalents"],
    "st_investments": ["CurrentInvestments", "ShorttermDepositsNotClassifiedAsCashEquivalents"],
    "lt_investments": [],
    "debt_total": ["Borrowings"],
    "debt_noncurrent": ["NoncurrentPortionOfNoncurrentBorrowings", "LongtermBorrowings"],
    "debt_current": ["CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings"],
    "short_borrowings": [],
    "leases": ["LeaseLiabilities"],
}
CURRENCY_SYMBOL = {"USD": "$", "MXN": "MX$", "EUR": "€", "GBP": "£", "JPY": "¥"}


class FilingsError(Exception):
    pass


def taxonomy(facts: dict) -> str:
    """'us-gaap' or 'ifrs-full', whichever the company actually reports in (a few IFRS filers carry a
    handful of stray US GAAP tags)."""
    f = facts.get("facts", {})
    g, i = len(f.get("us-gaap", {})), len(f.get("ifrs-full", {}))
    if not g and not i:
        raise FilingsError("The SEC has no XBRL financial statements for this company.")
    return "ifrs-full" if i > g else "us-gaap"


def currency(facts: dict) -> str:
    """Reporting currency: the unit of the newest annual revenue (or total assets). When a 20-F also shows
    that year in dollars for convenience, the currency with more rows (every comparative year) wins."""
    ns = taxonomy(facts)
    if ns == "us-gaap":
        return "USD"
    data = facts["facts"]["ifrs-full"]
    best = {}
    for tag in ("Revenue", "RevenueFromContractsWithCustomers", "Assets"):
        for unit, rows in data.get(tag, {}).get("units", {}).items():
            rows = [r for r in rows if r.get("form") in ANNUAL_FORMS]
            if len(unit) != 3 or not rows:
                continue
            end = max(r["end"] for r in rows)
            e, n = best.get(unit, ("", 0))
            best[unit] = (max(e, end), n + len(rows))
        if best:
            break
    if not best:
        raise FilingsError("Couldn't tell which currency this company reports in.")
    return max(best, key=lambda u: best[u])


def _gaap(facts: dict) -> dict:
    return facts.get("facts", {}).get(taxonomy(facts) if facts.get("facts") else "us-gaap", {})


def annual(facts: dict, tags: list[str], unit: str = "USD", ns: str | None = None) -> pd.Series:
    """Fiscal-year values indexed by fiscal year-end date. First tag with data wins,
    later tags only fill years the first one doesn't cover."""
    gaap = facts.get("facts", {}).get(ns, {}) if ns else _gaap(facts)
    combined = None
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


def _maps(facts: dict) -> tuple[dict, dict]:
    return (IFRS_TAGS, IFRS_BALANCE) if taxonomy(facts) == "ifrs-full" else (TAGS, BALANCE)


def balance_history(facts: dict, dates: pd.DatetimeIndex, unit: str = "USD") -> pd.DataFrame:
    """One row per fiscal year-end with the balance-sheet items the ratios need."""
    _, bal = _maps(facts)
    df = pd.DataFrame({k: _at(annual_instant(facts, tags, unit), dates) for k, tags in bal.items()}, index=dates)
    # Some filers tag only their notes as LongTermDebt and report finance leases inside the
    # current / non-current lines (Micron), so take whichever total is larger.
    parts = df["debt_noncurrent"].fillna(0) + df["debt_current"].fillna(0)
    df["debt"] = pd.concat([df["debt_total"].fillna(0), parts], axis=1).max(axis=1) + df["short_borrowings"].fillna(0)
    if "leases" in df:  # IFRS 16: leases are debt, because rent is already out of EBITDA
        df["debt"] += df["leases"].fillna(0)
    df["cash_all"] = df["cash"].fillna(0) + df["st_investments"].fillna(0) + df["lt_investments"].fillna(0)
    return df


def latest(facts: dict, tags: list[str], unit: str = "USD") -> dict | None:
    """Most recent balance-sheet value from an annual or interim report."""
    gaap, best = _gaap(facts), None
    for tag in tags:
        rows = [r for r in gaap.get(tag, {}).get("units", {}).get(unit, [])
                if r.get("form") in PERIODIC_FORMS and not r.get("start")]
        if rows:
            r = max(rows, key=lambda r: (r["end"], r.get("filed", "")))
            if best is None or r["end"] > best["end"]:
                best = {"val": float(r["val"]), "end": r["end"]}
    return best


def _recent(item: dict | None, ref: str | None, max_days: int = 400) -> dict | None:
    if not item or not ref:
        return item
    return item if (pd.Timestamp(ref) - pd.Timestamp(item["end"])).days <= max_days else None


def _dei_shares(facts: dict) -> dict | None:
    rows = facts.get("facts", {}).get("dei", {}).get("EntityCommonStockSharesOutstanding", {}).get("units", {}).get("shares", [])
    if not rows:
        return None
    last = max(rows, key=lambda r: (r.get("filed", ""), r["end"]))
    same = [r for r in rows if r.get("accn") == last.get("accn") and r["end"] == last["end"]]  # share classes
    return {"val": float(sum(r["val"] for r in same)), "end": last["end"], "source": "cover of latest filing"}


def shares(facts: dict) -> dict | None:
    if taxonomy(facts) == "ifrs-full":
        c = share_candidates(facts)
        return c[0] if c else None
    d = _dei_shares(facts)
    if d:
        return d
    diluted = annual(facts, ["WeightedAverageNumberOfDilutedSharesOutstanding"], unit="shares")
    if not diluted.empty:
        return {"val": float(diluted.iloc[-1]), "end": diluted.index[-1].date().isoformat(), "source": "diluted average"}
    return None


def share_candidates(facts: dict) -> list[dict]:
    """Local share counts a 20-F offers, best first: shares outstanding at year-end, the year's weighted
    average, then the cover page. Filers are not consistent (some count units or CPOs, a few tag the wrong
    scale), so the ADR logic checks them against the market value before using one."""
    out = []
    o = latest(facts, ["NumberOfSharesOutstanding"], unit="shares")
    w = annual(facts, ["WeightedAverageShares", "AdjustedWeightedAverageShares"], unit="shares")
    if o:
        out.append({**o, "source": "shares outstanding, 20-F"})
    if not w.empty:
        out.append({"val": float(w.iloc[-1]), "end": w.index[-1].date().isoformat(), "source": "weighted average shares, 20-F"})
    out.sort(key=lambda x: x["end"], reverse=True)  # newest first; ties keep the order above
    d = _dei_shares(facts)
    if d:  # the cover page last: some issuers count CPOs or units there
        out.append(d)
    return out


def _sum_tags(facts: dict, tag_lists: list[list[str]], unit: str) -> pd.Series:
    parts = [annual(facts, t, unit) for t in tag_lists if t]
    parts = [p for p in parts if not p.empty]
    if not parts:
        return pd.Series(dtype=float)
    out = parts[0]
    for p_ in parts[1:]:
        out = out.add(p_, fill_value=0.0)
    return out


def build(facts: dict) -> dict:
    ns = taxonomy(facts)
    ifrs = ns == "ifrs-full"
    tags, _ = _maps(facts)
    cur = currency(facts)
    form = "20-F" if ifrs else "10-K"
    notes = []
    if ifrs and cur != "USD":
        notes.append(f"Figures are in {cur}, the currency of the 20-F (IFRS).")
    A = lambda k: annual(facts, tags[k], cur)  # noqa: E731
    L = lambda k: latest(facts, tags[k], cur) if tags.get(k) else None  # noqa: E731
    rev, ni, ocf = A("revenue"), A("net_income"), A("ocf")
    capex = _sum_tags(facts, [tags["capex"], tags.get("capex_intangibles", [])], cur)
    if ocf.empty:
        raise FilingsError("Operating cash flow isn't in the SEC data, so free cash flow can't be computed.")
    if capex.empty:
        notes.append("Capex not found: free cash flow equals operating cash flow.")
    elif ifrs and not A("capex_intangibles").empty:
        notes.append("Capex includes purchases of intangible assets (concessions, software, licenses).")
    fcf = (ocf - capex.reindex(ocf.index).fillna(0.0)).dropna()

    cash = L("cash")
    ref = cash["end"] if cash else None
    sti = _recent(L("st_investments"), ref)
    lti = _recent(L("lt_investments"), ref)
    total = _recent(L("debt_total"), ref)
    split = [d for d in (_recent(L("debt_noncurrent"), ref), _recent(L("debt_current"), ref)) if d]
    # Take the larger of the tagged total and current + non-current (some filers tag only notes as the total).
    parts = split if sum(d["val"] for d in split) > (total["val"] if total else 0) else ([total] if total else [])
    sb = _recent(L("short_borrowings"), ref)
    if sb:
        parts.append(sb)
    debt = sum(p["val"] for p in parts)
    lease = 0.0
    if ifrs:
        lt = _recent(L("leases"), ref)
        if not lt:
            lp = [x for x in (_recent(latest(facts, [t], cur), ref) for t in tags["leases_parts"]) if x]
            lt = {"val": sum(x["val"] for x in lp)} if lp else None
        if lt and lt["val"] > 0:
            lease = lt["val"]
            debt += lease
            notes.append(f"Debt includes {lease / 1e9:,.1f}B of lease liabilities (IFRS 16 puts rent below EBITDA, "
                         "so leases count as debt).")
    cash_total = sum(x["val"] for x in (cash, sti, lti) if x)
    if lti:
        notes.append(f"Cash includes {lti['val'] / 1e9:,.1f}B of long-term marketable securities (liquid bonds).")
    if not cash:
        notes.append("Cash not found; assumed zero.")
    if not parts and not lease:
        notes.append(f"No debt found; assumed zero. Check the {form} if that looks wrong.")
    sh = shares(facts)
    if not sh:
        raise FilingsError("Shares outstanding aren't in the SEC data.")

    ebit, da, tax_exp, pretax, interest = (A(k) for k in ("ebit", "da", "tax_expense", "pretax", "interest"))
    gp, cogs, sbc = A("gross_profit"), A("cogs"), A("sbc")
    if gp.empty and not cogs.empty:
        gp = rev.sub(cogs, fill_value=None).dropna()
    if ifrs:
        # Operating profit isn't a required IFRS line, so some filers (FEMSA, Coca-Cola FEMSA) tag it with their
        # own element; that one is read from the newest 20-F. Last resort: pre-tax income + interest.
        ext = facts["facts"].get("ext", {})
        own = annual(facts, [t for t in ext if EXT_KEEP.search(t)], cur, ns="ext") if ext else pd.Series(dtype=float)
        if not own.empty and (ebit.empty or own.index.max() > ebit.index.max()):
            ebit = own.combine_first(ebit)
            notes.append("Operating profit comes from the company's own XBRL element in the 20-F (IFRS has no standard one).")
        elif ebit.empty and not pretax.empty:
            ebit = pretax.add(interest, fill_value=0)
            notes.append("Operating profit isn't tagged; EBIT = pre-tax income + interest.")
    elif ebit.empty and not pretax.empty:
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
    bal = balance_history(facts, rev.index, cur) if not rev.empty else pd.DataFrame()
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
        "name": facts.get("entityName", ""), "taxonomy": ns, "form": form, "currency": cur,
        "cur_symbol": CURRENCY_SYMBOL.get(cur, cur + " "), "leases": lease,
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
        "shares": sh["val"], "shares_source": sh["source"], "share_candidates": share_candidates(facts) if ifrs else [sh],
        "notes": notes,
        "gross_profit": tail(gp), "sbc": tail(sbc), "tax_expense": tail(tax_exp), "pretax": tail(pretax),
        "interest_hist": tail(interest), "balance": bal.iloc[-8:] if not bal.empty else bal,
        "nwc_pct": nwc_pct,
    }


MONEY_SERIES = ("revenue", "net_income", "ocf", "capex", "fcf", "ebit", "ebitda", "da", "gross_profit", "sbc",
                "tax_expense", "pretax", "interest_hist")
MONEY_VALUES = ("revenue0", "interest", "cash", "debt", "net_debt", "leases")


def convert(f: dict, rate: float, to: str = "USD") -> dict:
    """The same statements in another currency at one exchange rate (units of the new currency per unit
    of the old). Margins, growth and ratios don't change."""
    g = dict(f)
    for k in MONEY_SERIES:
        g[k] = f[k] * rate
    for k in MONEY_VALUES:
        g[k] = f[k] * rate if f.get(k) is not None else None
    if len(f["balance"]):
        g["balance"] = f["balance"] * rate
    g["currency"], g["cur_symbol"] = to, CURRENCY_SYMBOL.get(to, to + " ")
    return g


# --------------------------------------------------------------------------- newest annual report
def _local(tag: str) -> tuple[str, str]:
    ns, _, name = tag[1:].partition("}")
    return ns, name


STANDARD = ("xbrl.ifrs.org", "fasb.org", "xbrl.sec.gov", "xbrl.org/", "w3.org")
# Company-specific (extension) elements worth keeping: operating profit, which IFRS doesn't require as a line.
EXT_KEEP = re.compile(r"^(Operating(Income|Profit)(Loss)?|IncomeFromOperations|ProfitFromOperations)$")


def _family(ns_uri: str) -> str | None:
    if "xbrl.ifrs.org" in ns_uri and ns_uri.endswith("ifrs-full"):
        return "ifrs-full"
    if "fasb.org/us-gaap" in ns_uri:
        return "us-gaap"
    if "xbrl.sec.gov/dei" in ns_uri:
        return "dei"
    if not any(x in ns_uri for x in STANDARD):
        return "ext"
    return None


def parse_instance(xml: bytes, form: str, filed: str, accn: str = "", keep_ext: re.Pattern = EXT_KEEP) -> dict:
    """Facts of one XBRL instance document (the one EDGAR extracts from an inline 20-F or 10-K), in the
    same shape as the SEC's company facts. Only facts without dimensions (whole-company totals) are kept,
    plus the company's own operating-profit element under 'ext'."""
    contexts, units, raw = {}, {}, []
    depth = 0
    for ev, el in ET.iterparse(io.BytesIO(xml), events=("start", "end")):
        if ev == "start":
            depth += 1
            continue
        depth -= 1
        if depth != 1:
            continue
        _, name = _local(el.tag)
        if name == "context":
            dims = any(_local(x.tag)[1] in ("segment", "scenario") for x in el.iter())
            per = {(_local(x.tag)[1]): (x.text or "").strip() for x in el.iter() if _local(x.tag)[1] in ("startDate", "endDate", "instant")}
            contexts[el.get("id")] = None if dims else per
        elif name == "unit":
            measures = [(x.text or "").strip().split(":")[-1] for x in el.iter() if _local(x.tag)[1] == "measure"]
            units[el.get("id")] = "/".join(measures) if len(measures) <= 2 else None
        elif el.get("contextRef") is not None:
            fam = _family(_local(el.tag)[0])
            txt = (el.text or "").strip()
            if fam == "ext" and not keep_ext.search(name):
                fam = None
            if fam and txt:
                raw.append((fam, name, el.get("contextRef"), el.get("unitRef"), txt))
        el.clear()
    out: dict = {}
    seen = set()
    for fam, name, cref, uref, txt in raw:
        per = contexts.get(cref)
        unit = units.get(uref) if uref else None
        if not per or not unit:
            continue
        try:
            val = float(txt)
        except ValueError:
            continue
        if "instant" in per:
            row = {"end": per["instant"], "val": val}
        elif "startDate" in per and "endDate" in per:
            row = {"start": per["startDate"], "end": per["endDate"], "val": val}
        else:
            continue
        key = (fam, name, unit, row.get("start"), row["end"])
        if key in seen:
            continue
        seen.add(key)
        row.update({"form": form, "filed": filed, "accn": accn})
        out.setdefault(fam, {}).setdefault(name, {"units": {}})["units"].setdefault(unit, []).append(row)
    return out


def newest_filed(facts: dict) -> str:
    rows = (r for t in _gaap(facts).values() for u in t.get("units", {}).values() for r in u)
    return max((r.get("filed", "") for r in rows if r.get("form") in ANNUAL_FORMS), default="")


def merge(facts: dict, extra: dict) -> dict:
    """Company facts plus the facts of a newer filing, without touching the (cached) original."""
    f = dict(facts)
    f["facts"] = dict(facts.get("facts", {}))
    for fam, tags in extra.items():
        ns = dict(f["facts"].get(fam, {}))
        for tag, d in tags.items():
            old = ns.get(tag, {"units": {}})
            units = dict(old.get("units", {}))
            for u, rows in d["units"].items():
                units[u] = list(units.get(u, [])) + rows
            ns[tag] = {**old, "units": units}
        f["facts"][fam] = ns
    return f
