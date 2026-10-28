import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import fundamentals as F  # noqa: E402
import valuation as V  # noqa: E402


def test_eva_matches_the_seminar_problem():
    """'Problema EVA' (Alfa S.A.): sales 8,000, operating costs 5,200, depreciation 300, tax 30%,
    debt 1,300 at 6%, equity 4,000 at 12%, total assets 6,000, non-financial current liabilities 700."""
    ebit = 8000 - 5200 - 300
    w = V.wacc(ke=0.12, kd=0.06, tax=0.30, equity=4000, debt=1300)
    assert w == pytest.approx(4000 / 5300 * 0.12 + 1300 / 5300 * 0.06 * 0.7)
    e = F.eva(ebit, 0.30, w, capital=6000 - 700)
    assert e["nopat"] == pytest.approx(1750)
    assert e["capital"] == 5300
    assert e["eva"] == pytest.approx(1750 - w * 5300)
    assert e["eva"] > 0  # creates value: ROIC 33% vs WACC about 10.1%
    assert e["roic"] == pytest.approx(1750 / 5300)


def _f():
    idx = pd.to_datetime(["2023-12-31", "2024-12-31", "2025-12-31"])
    s = lambda *v: pd.Series(v, index=idx, dtype=float)  # noqa: E731
    bal = pd.DataFrame({"assets": [1000, 1100, 1200], "equity": [500, 550, 600], "debt": [200, 200, 200],
                        "cash_all": [100, 120, 150], "cash": [100, 120, 150], "st_investments": [0, 0, 0], "assets_current": [400, 420, 450], "liabilities_current": [200, 210, 300],
                        "receivables": [100, 110, 200], "inventory": [50, 55, 60], "payables": [80, 85, 90]}, index=idx)
    return {"revenue": s(1000, 1100, 1210), "net_income": s(100, 110, 130), "ocf": s(150, 160, 100),
            "ebit": s(150, 165, 190), "ebitda": s(200, 220, 250), "fcf": s(90, 100, 60), "gross_profit": s(400, 440, 490),
            "interest_hist": s(10, 10, 10), "sbc": s(5, 5, 5), "balance": bal}


def test_ratios_by_hand():
    t = F.table(_f())
    last = t["FY2025"]
    assert last["Revenue growth"] == pytest.approx(0.10)
    assert last["Current ratio"] == pytest.approx(450 / 300)
    assert last["Quick ratio"] == pytest.approx((150 + 200) / 300)
    assert last["ROE"] == pytest.approx(130 / 575)  # average equity
    dupont = last["DuPont · net margin"] * last["DuPont · asset turnover"] * last["DuPont · equity multiplier"]
    assert dupont == pytest.approx(last["ROE"])
    assert last["Interest coverage (EBIT / interest)"] == pytest.approx(19)
    assert last["Receivables growth − revenue growth"] == pytest.approx(200 / 110 - 1 - 0.10)
    assert last["Year-end receivables, days of sales"] == pytest.approx(200 / 1210 * 365)


def test_flags_spot_weak_cash_conversion_and_receivables():
    msgs = dict((m, k) for k, m in F.flags(F.table(_f())))
    kinds = list(msgs.values())
    assert kinds.count("watch") >= 2


def test_eva_history_uses_average_capital():
    h = F.eva_history(_f(), tax=0.25, wacc=0.10)
    cap = ((200 + 550) + (200 + 600)) / 2
    assert h.loc[2025, "capital"] == pytest.approx(cap)
    assert h.loc[2025, "eva"] == pytest.approx(190 * 0.75 - 0.10 * cap)
