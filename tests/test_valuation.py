import os
import sys
from dataclasses import replace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import valuation as V  # noqa: E402

BASE = V.Inputs(revenue0=1000.0, growth=0.10, margin0=0.30, margin_target=0.30, da_pct=0.05, capex_pct=0.05,
                nwc_pct=0.10, tax=0.20, wacc=0.09, ke=0.10, kd=0.05, tg=0.025, exit_mult=12.0,
                debt0=500.0, cash0=200.0, shares=100.0)


def test_projection_by_hand_year_one():
    p = V.project(BASE).loc[1]
    assert p.revenue == pytest.approx(1100)
    assert p.ebitda == pytest.approx(330)
    assert p.ebit == pytest.approx(330 - 55)
    # FCFF = EBIT(1-t) + D&A - capex - dNWC = 275*0.8 + 55 - 55 - 10
    assert p.fcff == pytest.approx(275 * 0.8 - 10)
    # FCFE = FCFF - interest(1-t) + net borrowing = FCFF - 500*0.05*0.8 + 50
    assert p.fcfe == pytest.approx(p.fcff - 20 + 50)


def test_margin_path_is_linear_to_target():
    p = V.project(replace(BASE, margin0=0.10, margin_target=0.30))
    assert list(p.margin.round(4)) == [0.14, 0.18, 0.22, 0.26, 0.30]


def test_unlevered_equity_bridge():
    v = V.value(BASE)
    u = v["unlevered"]["perpetuity"]
    assert u["equity"] == pytest.approx(u["ev"] - 300)
    assert u["per_share"] == pytest.approx(u["equity"] / 100)


def test_exit_multiple_tv_matches_ebitda():
    v = V.value(BASE)
    last = v["projection"].iloc[-1]
    expected_ev = v["pv_fcff"] + last.ebitda * 12 / 1.09 ** 5
    assert v["unlevered"]["exit"]["ev"] == pytest.approx(expected_ev)


def test_cross_checks_are_consistent():
    v = V.value(BASE)
    # Using the implied exit multiple as the exit multiple reproduces the perpetuity EV.
    v2 = V.value(replace(BASE, exit_mult=v["implied_exit_mult"]))
    assert v2["unlevered"]["exit"]["ev"] == pytest.approx(v["unlevered"]["perpetuity"]["ev"])
    # And the implied growth of an exit multiple gives back that multiple's EV.
    v3 = V.value(replace(BASE, tg=v["implied_tg"]))
    assert v3["unlevered"]["perpetuity"]["ev"] == pytest.approx(v["unlevered"]["exit"]["ev"])


def test_higher_wacc_lowers_value():
    assert V.value(replace(BASE, wacc=0.11))["unlevered"]["perpetuity"]["per_share"] < \
        V.value(BASE)["unlevered"]["perpetuity"]["per_share"]


def test_reverse_dcf_recovers_growth():
    price = V.value(replace(BASE, growth=0.17))["unlevered"]["perpetuity"]["per_share"]
    assert V.implied_growth(BASE, price) == pytest.approx(0.17, abs=1e-4)


def test_wacc_weights():
    assert V.wacc(0.10, 0.05, 0.2, equity=800, debt=200) == pytest.approx(0.8 * 0.10 + 0.2 * 0.05 * 0.8)


def test_rejects_growth_above_discount_rate():
    with pytest.raises(ValueError):
        V.value(replace(BASE, tg=0.10))


def test_verdict_bands():
    assert V.verdict(130, 100)[0] == "Undervalued"
    assert V.verdict(105, 100)[0] == "Fairly valued"
    assert V.verdict(80, 100)[0] == "Overvalued"


def test_terminal_year_is_normalized_to_perpetual_growth():
    # When explicit growth equals perpetual growth, the normalized year 6 is just year 5 grown at g.
    a = replace(BASE, growth=0.025)
    v = V.value(a)
    last = v["projection"].iloc[-1]
    assert v["terminal"]["fcff"] == pytest.approx(last["fcff"] * 1.025)
    assert v["terminal"]["fcfe"] == pytest.approx(last["fcfe"] * 1.025)


def test_faster_growth_does_not_leak_into_terminal_working_capital():
    v = V.value(replace(BASE, growth=0.30))
    last, term = v["projection"].iloc[-1], v["terminal"]
    rev6 = last["revenue"] * 1.025
    ebit6 = rev6 * 0.30 - rev6 * 0.05
    expected = ebit6 * 0.8 + rev6 * 0.05 - rev6 * 0.05 - (rev6 - last["revenue"]) * 0.10
    assert term["fcff"] == pytest.approx(expected)


def test_implied_growth_round_trip():
    v = V.value(BASE)
    a2 = replace(BASE, tg=v["implied_tg"])
    assert V.value(a2)["unlevered"]["perpetuity"]["ev"] == pytest.approx(v["unlevered"]["exit"]["ev"], rel=1e-6)


def test_scenarios_are_ordered_and_weighted():
    sc = V.scenario_inputs(BASE)
    vals = {k: V.value(x)["average"] for k, x in sc.items()}
    assert vals["Bear"] < vals["Base"] < vals["Bull"]
    w = V.weighted(vals, {"Bear": 1, "Base": 2, "Bull": 1})
    assert w == pytest.approx((vals["Bear"] + 2 * vals["Base"] + vals["Bull"]) / 4)


def test_adjusted_beta_pulls_toward_one():
    assert V.adjusted_beta(2.0) == pytest.approx(1.67)
    assert V.adjusted_beta(1.0) == pytest.approx(1.0)
    assert V.adjusted_beta(None) == 1.0
