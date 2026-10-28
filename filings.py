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
    "debt_total": ["LongTermDebt"],
    "debt_noncurrent": ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"],
    "debt_current": ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"],
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
    total = _recent(latest(facts, TAGS["debt_total"]), ref)
    parts = [total] if total else [d for d in (_recent(latest(facts, TAGS["debt_noncurrent"]), ref),
                                               _recent(latest(facts, TAGS["debt_current"]), ref)) if d]
    sb = _recent(latest(facts, TAGS["short_borrowings"]), ref)
    if sb:
        parts.append(sb)
    cash_total = (cash["val"] if cash else 0.0) + (sti["val"] if sti else 0.0)
    debt = sum(p["val"] for p in parts)
    if not cash:
        notes.append("Cash not found; assumed zero.")
    if not parts:
        notes.append("No debt found; assumed zero. Check the 10-K if that looks wrong.")
    sh = shares(facts)
    if not sh:
        raise FilingsError("Shares outstanding aren't in the SEC data.")

    tail = lambda s: s.iloc[-8:]  # noqa: E731
    return {
        "name": facts.get("entityName", ""),
        "revenue": tail(rev), "net_income": tail(ni), "ocf": tail(ocf), "capex": tail(capex), "fcf": tail(fcf),
        "cash": cash_total, "debt": debt, "net_debt": debt - cash_total, "balance_date": ref,
        "shares": sh["val"], "shares_source": sh["source"], "notes": notes,
    }
