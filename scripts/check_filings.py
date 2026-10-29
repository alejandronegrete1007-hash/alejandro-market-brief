"""Print the DCF inputs the app derives from SEC filings, to check them against the 10-K.

Run by .github/workflows/checks.yml (the SEC API needs no key, only a User-Agent).
Each ticker's numbers are emitted as a GitHub annotation so they can be read without logs.
"""
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import adr  # noqa: E402
import filings  # noqa: E402

UA = {"User-Agent": "Alejandro Market Brief data check alejandronegrete1007@gmail.com"}
TICKERS = os.environ.get("CHECK_TICKERS", "MU,AAPL,AMX,FMX,KOF,CX,ASR,PAC,OMAB,TV,TSM").split(",")


def get(url, raw=False):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
        b = r.read()
    return b if raw else json.loads(b)


def top_up(cik, facts):
    """Same as sources.sec_facts_full: add the newest 20-F when company facts lag."""
    if filings.taxonomy(facts) != "ifrs-full":
        return facts, ""
    rec = get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")["filings"]["recent"]
    filed, accn, form = next((d, a, fm) for d, a, fm in zip(rec["filingDate"], rec["accessionNumber"], rec["form"])
                             if fm in ("20-F", "20-F/A", "40-F", "40-F/A"))
    if filed <= filings.newest_filed(facts):
        return facts, f"facts current ({filed})"
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/"
    names = [i["name"] for i in get(base + "index.json")["directory"]["item"]]
    inst = [n for n in names if n.endswith("_htm.xml")][0]
    xml = get(base + inst, raw=True)
    extra = filings.parse_instance(xml, form.split("/")[0], filed, accn)
    if os.environ.get("PROBE_TAGS"):
        rx = re.compile(r"Borrow|Debt|Notes|Bond|Debenture|Payable|Purchase|Payment|Operating|Acquire|Concession|Addition|Loan")
        wide = filings.parse_instance(xml, form.split("/")[0], filed, accn, keep_ext=rx)
        out = []
        for fam in ("ifrs-full", "ext"):
            for tag, d in wide.get(fam, {}).items():
                if not rx.search(tag):
                    continue
                for u, rows in d["units"].items():
                    last = max(rows, key=lambda r: r["end"])
                    if last["end"] >= "2025-06":
                        out.append(f"{fam[:3]}:{tag}[{u}{'D' if last.get('start') else 'I'}]={last['val'] / 1e9:.2f}B")
        msg = " | ".join(out)
        for i in range(0, len(msg), 3500):
            print(f"::notice title=TAGS {cik}#{i // 3500}::{msg[i:i + 3500]}")
    return filings.merge(facts, extra), f"topped up with {form} filed {filed}"


def b(x):
    return "n/a" if x is None else f"{x / 1e9:,.2f}B"


def p(x):
    return "n/a" if x is None else f"{x:.1%}"


ciks = {v["ticker"].upper(): int(v["cik_str"]) for v in get("https://www.sec.gov/files/company_tickers.json").values()}
for t in TICKERS:
    t = t.strip().upper()
    try:
        facts, how = top_up(ciks[t], get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{ciks[t]:010d}.json"))
        f = filings.build(facts)
        lb = f["balance"].iloc[-1] if len(f["balance"]) else {}
        bal = ", ".join(f"{k} {b(lb.get(k)) if lb.get(k) == lb.get(k) else 'n/a'}" for k in
                        ("assets", "equity", "debt", "cash_all", "receivables", "inventory", "payables",
                         "assets_current", "liabilities_current")) if len(lb) else "n/a"
        cands = "; ".join(f"{c['val'] / 1e6:,.0f}M {c['source']} @{c['end']} -> {c['val'] / adr.RATIO.get(t, 1) / 1e6:,.1f}M ADR"
                          for c in f["share_candidates"])
        hist = " | ".join(f"FY{d.year}: rev {b(r)} ebit {b(f['ebit'].get(d))} ebitda {b(f['ebitda'].get(d))} "
                          f"fcf {b(f['fcf'].get(d))}" for d, r in f["revenue"].iloc[-3:].items())
        msg = (f"{f['currency']} {f['form']} {how} | FY end {f['fiscal_end']} | revenue {b(f['revenue0'])} | EBITDA margin {p(f['ebitda_margin'])} "
               f"(3y avg {p(f['ebitda_margin_3y'])}) | D&A {p(f['da_pct'])} | capex {p(f['capex_pct'])} | tax {p(f['tax_rate'])} | "
               f"interest {b(f['interest'])} | cash {b(f['cash'])} | debt {b(f['debt'])} | balance {f['balance_date']} | "
               f"shares {cands} | leases {b(f.get('leases'))} | nwc {p(f.get('nwc_pct'))} | "
               f"balance FY: {bal} | {hist} | notes: {'; '.join(f['notes']) or 'none'}")
    except Exception as e:  # report and continue
        msg = f"ERROR {type(e).__name__}: {e}"
    print(f"{t}: {msg}")
    for i in range(0, len(msg), 3500):
        print(f"::notice title={t}#{i // 3500}::{msg[i:i + 3500]}")
