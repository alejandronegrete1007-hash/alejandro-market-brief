"""IFRS (20-F) path: reading an XBRL instance, picking the reporting currency, building the DCF inputs,
and turning local shares into ADRs."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import adr  # noqa: E402
import filings  # noqa: E402

XML = b"""<?xml version="1.0" encoding="utf-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:iso4217="http://www.xbrl.org/2003/iso4217"
  xmlns:ifrs-full="https://xbrl.ifrs.org/taxonomy/2025-03-27/ifrs-full" xmlns:dei="http://xbrl.sec.gov/dei/2025"
  xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:amx="http://www.americamovil.com/20251231">
  <xbrli:context id="FY25"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>
  <xbrli:context id="FY24"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:startDate>2024-01-01</xbrli:startDate><xbrli:endDate>2024-12-31</xbrli:endDate></xbrli:period></xbrli:context>
  <xbrli:context id="I25"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period></xbrli:context>
  <xbrli:context id="FY25_seg"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1</xbrli:identifier>
    <xbrli:segment><xbrldi:explicitMember dimension="ifrs-full:SegmentsAxis">amx:MexicoMember</xbrldi:explicitMember></xbrli:segment></xbrli:entity>
    <xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>
  <xbrli:unit id="MXN"><xbrli:measure>iso4217:MXN</xbrli:measure></xbrli:unit>
  <xbrli:unit id="USD"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
  <xbrli:unit id="sh"><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unit>
  <ifrs-full:Revenue contextRef="FY25" unitRef="MXN" decimals="-3">943640000000</ifrs-full:Revenue>
  <ifrs-full:Revenue contextRef="FY24" unitRef="MXN" decimals="-3">869220000000</ifrs-full:Revenue>
  <ifrs-full:Revenue contextRef="FY25" unitRef="USD" decimals="-6">51000000000</ifrs-full:Revenue>
  <ifrs-full:Revenue contextRef="FY25_seg" unitRef="MXN" decimals="-3">300000000000</ifrs-full:Revenue>
  <ifrs-full:NumberOfSharesOutstanding contextRef="I25" unitRef="sh" decimals="0">60544000000</ifrs-full:NumberOfSharesOutstanding>
  <amx:OperatingIncome contextRef="FY25" unitRef="MXN" decimals="-3">191400000000</amx:OperatingIncome>
  <amx:SomethingElse contextRef="FY25" unitRef="MXN" decimals="-3">1</amx:SomethingElse>
</xbrli:xbrl>"""


def test_parse_instance_keeps_whole_company_facts_only():
    out = filings.parse_instance(XML, "20-F", "2026-04-28", "acc")
    rev = out["ifrs-full"]["Revenue"]["units"]
    assert sorted(r["val"] for r in rev["MXN"]) == [869220000000, 943640000000]  # the segment fact is dropped
    assert rev["USD"][0]["val"] == 51000000000
    assert out["ifrs-full"]["NumberOfSharesOutstanding"]["units"]["shares"][0] == {
        "end": "2025-12-31", "val": 60544000000, "form": "20-F", "filed": "2026-04-28", "accn": "acc"}
    assert list(out["ext"]) == ["OperatingIncome"]  # company elements: only operating profit (and capex) are kept


def _row(y, v, form="20-F"):
    return {"start": f"{y}-01-01", "end": f"{y}-12-31", "val": v, "form": form, "filed": f"{y + 1}-04-20"}


def _inst(y, v):
    return {"end": f"{y}-12-31", "val": v, "form": "20-F", "filed": f"{y + 1}-04-20"}


def _facts():
    years = [2021, 2022, 2023, 2024]
    rev = [100.0, 110.0, 121.0, 133.1]
    d = lambda k: [_row(y, r * k) for y, r in zip(years, rev)]  # noqa: E731
    b = lambda k: [_inst(y, r * k) for y, r in zip(years, rev)]  # noqa: E731
    return {"entityName": "Demo SAB", "facts": {"ifrs-full": {
        # pesos every year, plus a dollar "convenience translation" of the last year only
        "Revenue": {"units": {"MXN": d(1), "USD": [_row(2024, 7.0)]}},
        "ProfitLossFromOperatingActivities": {"units": {"MXN": d(0.2)}},
        "DepreciationAndAmortisationExpense": {"units": {"MXN": d(0.1)}},
        "CashFlowsFromUsedInOperatingActivities": {"units": {"MXN": d(0.25)}},
        "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities": {"units": {"MXN": d(0.08)}},
        "PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities": {"units": {"MXN": d(0.02)}},
        "ProfitLossBeforeTax": {"units": {"MXN": d(0.15)}},
        "IncomeTaxExpenseContinuingOperations": {"units": {"MXN": d(0.045)}},
        "InterestExpense": {"units": {"MXN": d(0.03)}},
        "CashAndCashEquivalents": {"units": {"MXN": b(0.1)}},
        "Borrowings": {"units": {"MXN": b(0.5)}},
        "LeaseLiabilities": {"units": {"MXN": b(0.1)}},
        "Assets": {"units": {"MXN": b(2)}},
        "EquityAttributableToOwnersOfParent": {"units": {"MXN": b(0.8)}},
        "TradeAndOtherCurrentReceivables": {"units": {"MXN": b(0.2)}},
        "Inventories": {"units": {"MXN": b(0.05)}},
        "TradeAndOtherCurrentPayables": {"units": {"MXN": b(0.15)}},
        "NumberOfSharesOutstanding": {"units": {"shares": [_inst(2024, 2_000.0)]}},
    }}}


def test_currency_ignores_the_convenience_translation():
    assert filings.taxonomy(_facts()) == "ifrs-full"
    assert filings.currency(_facts()) == "MXN"


def test_build_reads_ifrs_in_pesos_with_leases_as_debt():
    f = filings.build(_facts())
    assert f["form"] == "20-F" and f["currency"] == "MXN" and f["cur_symbol"] == "MX$"
    assert f["revenue0"] == pytest.approx(133.1)
    assert f["ebitda_margin"] == pytest.approx(0.30)
    assert f["capex_pct"] == pytest.approx(0.10)  # PP&E + intangibles
    assert f["tax_rate"] == pytest.approx(0.30)
    assert f["debt"] == pytest.approx(133.1 * 0.6)  # borrowings + IFRS 16 leases
    assert f["nwc_pct"] == pytest.approx(0.10)
    assert f["shares"] == 2_000.0


def test_newer_filing_tops_up_company_facts():
    extra = filings.parse_instance(XML, "20-F", "2026-04-28")
    merged = filings.merge(_facts(), extra)
    f = filings.build(merged)
    assert f["fiscal_end"] == "2025-12-31" and f["revenue0"] == 943640000000
    assert "Revenue" in _facts()["facts"]["ifrs-full"]  # the original is untouched
    assert len(_facts()["facts"]["ifrs-full"]["Revenue"]["units"]["MXN"]) == 4


def test_operating_profit_from_company_element_when_ifrs_has_none():
    facts = _facts()
    del facts["facts"]["ifrs-full"]["ProfitLossFromOperatingActivities"]
    facts["facts"]["ext"] = {"OperatingIncome": {"units": {"MXN": [_row(2024, 30.0)]}}}
    f = filings.build(facts)
    assert f["ebit"].iloc[-1] == 30.0
    assert any("own XBRL element" in n for n in f["notes"])


def test_convert_scales_money_but_not_ratios():
    f = filings.build(_facts())
    g = filings.convert(f, 0.05)
    assert g["revenue0"] == pytest.approx(133.1 * 0.05) and g["debt"] == pytest.approx(f["debt"] * 0.05)
    assert g["ebitda_margin"] == f["ebitda_margin"] and g["currency"] == "USD"


def test_ads_count_divides_by_the_ratio_and_checks_market_value():
    cands = [{"val": 505_277_000_000, "source": "weighted average", "end": "2025-12-31"},  # tagged 1000x too big
             {"val": 505_277_000, "source": "shares outstanding", "end": "2024-12-31"}]
    n, how = adr.ads_count("PAC", cands, price=230.0, mcap_usd=50_527_700 * 230.0)
    assert n == pytest.approx(50_527_700) and "÷ 10" in how
    n, how = adr.ads_count("PAC", cands, price=230.0, mcap_usd=None)  # no market data: the scale error is caught anyway
    assert n == pytest.approx(50_527_700) and "thousands" in how
    n, how = adr.ads_count("PAC", cands[1:], price=230.0, mcap_usd=1e9)  # counts far from the market value
    assert n == pytest.approx(1e9 / 230) and "market cap" in how
    n, _ = adr.ads_count("AMX", [{"val": 60_544e6, "source": "x", "end": "2025-12-31"}], price=24.0, mcap_usd=None)
    assert n == pytest.approx(3_027.2e6)


def test_peso_dcf_per_adr_equals_peso_value_over_adrs_times_fx():
    """Running the model in pesos with shares = ADRs x FIX gives dollars per ADR directly."""
    import valuation as V
    a = V.Inputs(revenue0=900e9, growth=0.06, margin0=0.39, margin_target=0.39, da_pct=0.18, capex_pct=0.14,
                 nwc_pct=0.05, tax=0.30, wacc=0.11, ke=0.13, kd=0.10, tg=0.045, exit_mult=6.5,
                 debt0=740e9, cash0=35e9, shares=3_027e6 * 18.7)
    v = V.value(a)
    peso_equity = v["unlevered"]["perpetuity"]["equity"]
    assert v["unlevered"]["perpetuity"]["per_share"] == pytest.approx(peso_equity / 18.7 / 3_027e6)
