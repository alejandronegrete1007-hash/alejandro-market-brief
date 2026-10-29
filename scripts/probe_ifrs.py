"""Probe SEC XBRL company facts of Mexican ADR issuers (20-F, IFRS): which taxonomies, tags and units exist."""
import json
import sys
import urllib.request

UA = {"User-Agent": "Alejandro Market Brief data check alejandronegrete1007@gmail.com"}
SYMS = sys.argv[1:] or ["AMX", "FMX", "KOF", "CX", "ASR", "PAC", "OMAB", "TV"]
WANT = ["Revenue", "ProfitLossFromOperatingActivities", "ProfitLoss", "ProfitLossAttributableToOwnersOfParent",
        "DepreciationAndAmortisationExpense", "DepreciationAmortisationAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss",
        "CashFlowsFromUsedInOperatingActivities", "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
        "CashAndCashEquivalents", "Borrowings", "NoncurrentPortionOfNoncurrentBorrowings", "CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings",
        "Equity", "EquityAttributableToOwnersOfParent", "Assets", "CurrentAssets", "CurrentLiabilities", "IncomeTaxExpenseContinuingOperations",
        "ProfitLossBeforeTax", "FinanceCosts", "InterestExpense", "TradeAndOtherCurrentReceivables", "Inventories",
        "TradeAndOtherCurrentPayables", "GrossProfit", "CostOfSales", "LeaseLiabilities"]


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.load(r)


ciks = {v["ticker"].upper(): int(v["cik_str"]) for v in get("https://www.sec.gov/files/company_tickers.json").values()}
for t in SYMS:
    try:
        f = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{ciks[t]:010d}.json")
        facts = f.get("facts", {})
        ns = {k: len(v) for k, v in facts.items()}
        ifrs = facts.get("ifrs-full", {})
        parts = []
        for tag in WANT:
            if tag in ifrs:
                units = ifrs[tag]["units"]
                u = next(iter(units))
                rows = [r for r in units[u] if r.get("form", "").startswith("20-F")]
                last = max(rows, key=lambda r: (r["end"], r.get("filed", ""))) if rows else None
                parts.append(f"{tag}[{u}]={last['val'] / 1e9:.2f}B@{last['end']}" if last else f"{tag}[{u}]=no20F")
        dei = facts.get("dei", {}).get("EntityCommonStockSharesOutstanding", {}).get("units", {}).get("shares", [])
        last_sh = sorted(dei, key=lambda r: r.get("filed", ""))[-3:]
        sh = "; ".join(f"{r['val'] / 1e6:,.0f}M ({r.get('fy')}, {r.get('frame', '')})" for r in last_sh)
        msg = f"ns={ns} | {' | '.join(parts)} | shares: {sh}"
    except Exception as e:
        msg = f"ERROR {type(e).__name__}: {e}"
    print(f"{t}: {msg}")
    print(f"::notice title={t}::{msg[:3800]}")
