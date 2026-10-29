"""Second IFRS probe: revenue / share-count tags with all units, the newest 20-F in companyfacts vs EDGAR submissions."""
import json
import sys
import urllib.request

UA = {"User-Agent": "Alejandro Market Brief data check alejandronegrete1007@gmail.com"}
SYMS = sys.argv[1:] or ["AMX", "FMX", "KOF", "CX", "ASR", "PAC", "OMAB", "TV", "TSM", "NVO"]
KEYS = ("Revenue", "Shares", "OperatingActivities", "PropertyPlantAndEquipment", "Borrowings", "Depreciation",
        "ProfitLossFromOperating", "OperatingProfit")


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.load(r)


ciks = {v["ticker"].upper(): int(v["cik_str"]) for v in get("https://www.sec.gov/files/company_tickers.json").values()}
for t in SYMS:
    try:
        cik = ciks[t]
        f = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")
        sub = get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")["filings"]["recent"]
        f20 = [(d, fm) for d, fm in zip(sub["filingDate"], sub["form"]) if fm.startswith(("20-F", "40-F", "6-K"))][:3]
        ifrs = f.get("facts", {}).get("ifrs-full", {})
        all_rows = [r for tag in ifrs.values() for u in tag["units"].values() for r in u]
        newest = max((r.get("filed", "") for r in all_rows), default="")
        forms = sorted({r.get("form") for r in all_rows})
        parts = []
        for tag, d in ifrs.items():
            if not any(k in tag for k in KEYS):
                continue
            for u, rows in d["units"].items():
                rows = [r for r in rows if r.get("form", "").startswith("20-F")]
                if not rows:
                    continue
                last = max(rows, key=lambda r: (r["end"], r.get("filed", "")))
                if last["end"] < "2023":
                    continue
                dur = "D" if last.get("start") else "I"
                parts.append(f"{tag}[{u},{dur}]={last['val']:.4g}@{last['end']}")
        msg = f"filings={f20} newest_fact_filed={newest} forms={forms} | " + " | ".join(parts)
    except Exception as e:
        msg = f"ERROR {type(e).__name__}: {e}"
    print(f"{t}: {msg}")
    for i in range(0, len(msg), 3500):
        print(f"::notice title={t}#{i // 3500}::{msg[i:i + 3500]}")
