"""From local shares to the security traded in New York.

A US-listed ADR (or GDS) is a certificate for several local shares, so a value per local share has to be
multiplied by the ratio, and by the exchange rate when the company reports in pesos. Ratios come from the
depositary terms printed on each 20-F cover. Share counts in the XBRL data are not always comparable (some
issuers count units or CPOs, one tags the wrong scale), so the count is checked against the market value
before it is used.
"""
from __future__ import annotations

# local shares per ADR / GDS
RATIO = {
    "AMX": 20,    # 20 Series B shares
    "FMX": 50,    # 10 BD units; a BD unit = 1 B + 2 D-B + 2 D-L shares
    "KOF": 80,    # 10 units; a unit = 3 Series B + 5 Series L shares
    "CX": 30,     # 10 CPOs; a CPO = 2 Series A + 1 Series B shares
    "ASR": 10,    # 10 Series B shares
    "PAC": 10,    # 10 Series B shares
    "OMAB": 8,    # 8 Series B shares
    "TV": 585,    # 5 CPOs; a CPO = 117 shares (A, B, D and L)
    "TSM": 5,
    "NVO": 1,
    "SAP": 1,
}


def ads_count(sym: str, candidates: list[dict], price: float, mcap_usd: float | None) -> tuple[float, str]:
    """Number of ADR-equivalents (local shares / ratio) and where it came from.

    Each local count the filing offers is divided by the ratio; the first whose implied market value is
    within a factor of two of the market data is used. If none is, the count implied by the market value
    itself (market cap / price) is used and said so."""
    ratio = RATIO.get(sym.upper(), 1)
    unit = "ADR" if ratio != 1 or sym.upper() in RATIO else "share"
    for c in candidates:
        n = c["val"] / ratio
        if not mcap_usd or not price or 0.5 <= n * price / mcap_usd <= 2:
            how = f"{c['val'] / 1e6:,.0f}M local shares ÷ {ratio} per {unit} ({c['source']})" if ratio != 1 else c["source"]
            return n, how
    if mcap_usd and price:
        return mcap_usd / price, "market cap ÷ price (the share counts in the filing didn't match the market value)"
    raise ValueError("No usable share count.")
