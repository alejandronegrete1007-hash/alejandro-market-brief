"""One-off: Treasury yields by date from FRED's public CSV, to see which day each app calls 'a month ago'."""
import csv
import io
import urllib.request

IDS = "DGS1MO,DGS3MO,DGS6MO,DGS1,DGS2,DGS5,DGS10,DGS30"
url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={IDS}&cosd=2026-09-15&coed=2026-10-28"
rows = list(csv.reader(io.StringIO(urllib.request.urlopen(url, timeout=60).read().decode())))
lines = [" ".join(r) for r in rows]
msg = " || ".join(lines)
for i in range(0, len(msg), 3800):
    print(f"::notice title=curve#{i // 3800}::{msg[i:i + 3800]}")
