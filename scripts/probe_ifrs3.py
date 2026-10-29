"""Third IFRS probe: does the newest 20-F's XBRL instance (EDGAR archive) hold FY2025, when companyfacts stops at FY2024?"""
import json
import re
import sys
import time
import urllib.request

UA = {"User-Agent": "Alejandro Market Brief data check alejandronegrete1007@gmail.com"}
SYMS = sys.argv[1:] or ["AMX", "CX", "KOF", "PAC"]


def get(url, raw=False):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
        b = r.read()
    return b if raw else json.loads(b)


ciks = {v["ticker"].upper(): int(v["cik_str"]) for v in get("https://www.sec.gov/files/company_tickers.json").values()}
for t in SYMS:
    try:
        cik = ciks[t]
        sub = get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")["filings"]["recent"]
        rows = [(d, a, p) for d, a, fm, p in zip(sub["filingDate"], sub["accessionNumber"], sub["form"], sub["primaryDocument"])
                if fm in ("20-F", "20-F/A")]
        d, acc, prim = rows[0]
        base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/"
        idx = get(base + "index.json")
        names = [i["name"] for i in idx["directory"]["item"]]
        inst = [n for n in names if n.endswith("_htm.xml")] or [n for n in names if n.endswith(".xml") and "Financial" not in n and not n.startswith("FilingSummary")]
        t0 = time.time()
        x = get(base + inst[0], raw=True).decode("utf-8", "ignore")
        took = time.time() - t0
        rev = re.findall(r'<ifrs-full:Revenue[^>]*contextRef="([^"]+)"[^>]*unitRef="([^"]+)"[^>]*>([^<]+)<', x)[:4]
        ctx = re.findall(r'<xbrli:context id="([^"]+)">(.{0,400}?)</xbrli:context>', x, re.S)[:2]
        msg = (f"latest20F={d} {acc} primary={prim} instance={inst[:2]} size={len(x) / 1e6:.1f}MB in {took:.1f}s "
               f"ifrs_facts={x.count('<ifrs-full:')} rev={rev} ctx={[(c, re.sub(r'\\s+', ' ', b)[:200]) for c, b in ctx]} files={names[:25]}")
    except Exception as e:
        msg = f"ERROR {type(e).__name__}: {e}"
    print(f"{t}: {msg}")
    for i in range(0, len(msg), 3500):
        print(f"::notice title={t}#{i // 3500}::{msg[i:i + 3500]}")
