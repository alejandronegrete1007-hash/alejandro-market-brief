import math
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import filings  # noqa: E402
import quant as Q  # noqa: E402


def prices(values, start="2025-01-01"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


def test_ytd_uses_last_close_of_previous_year():
    s = pd.Series([90.0, 100.0, 110.0, 120.0],
                  index=pd.to_datetime(["2025-12-30", "2025-12-31", "2026-01-02", "2026-06-01"]))
    assert Q.ytd_return(s) == pytest.approx(0.20)


def test_volatility_of_constant_growth_is_zero():
    s = prices(100 * 1.001 ** np.arange(300))
    assert Q.annual_volatility(s) == pytest.approx(0.0, abs=1e-9)


def test_volatility_matches_simulated_sigma():
    rng = np.random.default_rng(0)
    s = prices(100 * np.exp(np.cumsum(rng.normal(0, 0.02, 3000))))
    assert Q.annual_volatility(s, window=3000) == pytest.approx(0.02 * math.sqrt(252), rel=0.05)


def test_max_drawdown():
    s = prices([100, 120, 60, 90, 130])
    assert Q.max_drawdown(s) == pytest.approx(-0.5)


def test_beta_of_levered_copy_is_two():
    rng = np.random.default_rng(1)
    b = prices(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, 600))))
    s = prices(100 * np.cumprod(1 + 2 * b.pct_change().fillna(0).values))
    assert Q.beta(s, b) == pytest.approx(2.0, rel=0.08)


def test_statistical_range_symmetric_in_log_space():
    r = Q.statistical_range(100, 0.30, 63)
    assert r.low68 * r.high68 == pytest.approx(100 ** 2)
    assert r.high95 > r.high68 > 100 > r.low68 > r.low95


def test_cagr_on_dates():
    s = pd.Series([100.0, 121.0], index=pd.to_datetime(["2020-12-31", "2022-12-31"]))
    s = pd.concat([pd.Series([110.0], index=pd.to_datetime(["2021-12-31"])), s]).sort_index()
    assert Q.cagr(s) == pytest.approx(0.10, abs=0.001)


def _row(start, end, val, filed, form="10-K"):
    return {"start": start, "end": end, "val": val, "filed": filed, "form": form}


def test_filings_annual_keeps_full_years_and_latest_restatement():
    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
        _row("2023-09-01", "2024-08-31", 100, "2024-10-01"),
        _row("2023-09-01", "2024-08-31", 105, "2025-10-01"),   # restated in the next 10-K
        _row("2024-06-01", "2024-08-31", 30, "2024-10-01"),    # a quarter inside the 10-K: ignored
        _row("2024-09-01", "2025-08-31", 130, "2025-10-01"),
    ]}}}}}
    s = filings.annual(facts, ["Revenues"])
    assert list(s.values) == [105, 130]
    assert s.index[-1] == pd.Timestamp("2025-08-31")


def test_filings_build_rejects_ifrs_filers():
    with pytest.raises(filings.FilingsError):
        filings.build({"facts": {"ifrs-full": {}}})
