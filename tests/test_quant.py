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


def test_rebased_starts_at_100_and_window_return():
    df = pd.DataFrame({"a": [50.0, 100.0, 150.0], "b": [10.0, 10.0, 12.0]},
                      index=pd.to_datetime(["2025-12-31", "2026-01-02", "2026-03-02"]))
    r = Q.rebased(df, Q.window_start(df.index[-1], "YTD"))
    assert list(r.iloc[0]) == [100.0, 100.0]
    assert r["a"].iloc[-1] == pytest.approx(300.0)
    assert Q.window_return(df["a"], Q.window_start(df.index[-1], "YTD")) == pytest.approx(2.0)


def test_alpha_zero_for_pure_beta_and_positive_with_drift():
    rng = np.random.default_rng(3)
    m = prices(100 * np.cumprod(1 + rng.normal(0.0004, 0.01, 400)))
    mr = m.pct_change().fillna(0).values
    copy = prices(100 * np.cumprod(1 + 1.5 * mr))
    assert Q.alpha(copy, m, rf=0.0) == pytest.approx(0.0, abs=0.01)
    drift = prices(100 * np.cumprod(1 + 1.5 * mr + 0.0004))
    assert Q.alpha(drift, m, rf=0.0) == pytest.approx(0.0004 * 252, rel=0.1)


def test_correlation_and_capture():
    rng = np.random.default_rng(4)
    m = prices(100 * np.cumprod(1 + rng.normal(0, 0.01, 600)))
    two_x = prices(100 * np.cumprod(1 + 2 * m.pct_change().fillna(0).values))
    assert Q.correlation(two_x, m) > 0.95
    up, dn = Q.capture(two_x, m)
    assert up == pytest.approx(2.0, rel=0.15) and dn == pytest.approx(2.0, rel=0.15)


def test_decompose_adds_up():
    d = Q.decompose(0.50, 0.30, 0.10)
    assert d == {"market": 0.10, "sector": pytest.approx(0.20), "stock": pytest.approx(0.20)}
    assert sum(d.values()) == pytest.approx(0.50)


def test_simulation_zero_drift_is_centred_on_today():
    rng = np.random.default_rng(5)
    c = prices(100 * np.exp(np.cumsum(rng.normal(0.003, 0.02, 600))))   # strong past uptrend
    paths = Q.simulate(c, horizon=126, n=6000)
    median_log = np.median(np.log(paths[:, -1] / c.iloc[-1]))
    assert abs(median_log) < 0.03                                          # the uptrend is not extrapolated
    f = Q.fan(paths)
    assert (f[5] <= f[50]).all() and (f[50] <= f[95]).all()
    assert Q.prob_touch(paths, c.iloc[-1] * 0.01, above=False) == 0.0


def test_tail_risk_on_fat_tailed_returns():
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(1)
    r = rng.standard_t(3, 600) * 0.01
    close = pd.Series(100 * np.exp(np.cumsum(r)), index=pd.bdate_range("2024-01-01", periods=600))
    t = Q.tail_risk(close)
    assert t["cvar"] > t["var"] > 0
    assert t["kurt"] > 1  # fat tails
    assert t["days"] == 504
