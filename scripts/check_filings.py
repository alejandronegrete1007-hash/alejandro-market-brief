"""Print the DCF inputs the app derives from SEC filings, to check them against the 10-K.

Run by .github/workflows/checks.yml (the SEC API needs no key, only a User-Agent).
Each ticker's numbers are emitted as a GitHub annotation so they can be read without logs.
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import filings  # noqa: E402

UA = {"User-Agent": "Alejandro Market Brief data check alejandronegrete1007@gmail.com"}
TICKERS = os.environ.get("CHECK_TICKERS", "MU,SNDK,DELL,MRNA,MPC,AAPL").split(",")


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.load(r)


def b(x):
    return "n/a" if x is None else f"{x / 1e9:,.2f}B"


def p(x):
    return "n/a" if x is None else f"{x:.1%}"


ciks = {v["ticker"].upper(): int(v["cik_str"]) for v in get("https://www.sec.gov/files/company_tickers.json").values()}
for t in TICKERS:
    t = t.strip().upper()
    try:
        f = filings.build(get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{ciks[t]:010d}.json"))
        lb = f["balance"].iloc[-1] if len(f["balance"]) else {}
        bal = ", ".join(f"{k} {b(lb.get(k)) if lb.get(k) == lb.get(k) else 'n/a'}" for k in
                        ("assets", "equity", "debt", "cash_all", "receivables", "inventory", "payables",
                         "assets_current", "liabilities_current")) if len(lb) else "n/a"
        hist = " | ".join(f"FY{d.year}: rev {b(r)} ebitda {b(f['ebitda'].get(d))}"
                          for d, r in f["revenue"].iloc[-4:].items())
        msg = (f"FY end {f['fiscal_end']} | revenue {b(f['revenue0'])} | EBITDA margin {p(f['ebitda_margin'])} "
               f"(3y avg {p(f['ebitda_margin_3y'])}) | D&A {p(f['da_pct'])} | capex {p(f['capex_pct'])} | tax {p(f['tax_rate'])} | "
               f"interest {b(f['interest'])} | cash {b(f['cash'])} | debt {b(f['debt'])} | balance {f['balance_date']} | "
               f"shares {f['shares'] / 1e6:,.0f}M ({f['shares_source']}) | nwc {p(f.get('nwc_pct'))} | "
               f"balance FY: {bal} | {hist} | notes: {'; '.join(f['notes']) or 'none'}")
    except Exception as e:  # report and continue
        msg = f"ERROR {type(e).__name__}: {e}"
    print(f"{t}: {msg}")
    print(f"::notice title={t}::{msg}")
