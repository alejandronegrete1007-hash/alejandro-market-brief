# Alejandro Market Brief

A personal markets dashboard covering **two markets, Wall Street and Mexico**, built in Python.
Every morning it answers three questions in about five minutes: what moved, why, and what my stocks are worth.

**Live app:** https://alejandro-market-brief.streamlit.app

## What it does

| Page | What you get |
|---|---|
| **Today** | Clickable cards for US indices (via ETFs), gold, oil, Bitcoin, the 10Y yield, the peso (Banxico FIX), Banxico's rate, inflation, CETES, TIIE and the real policy rate. An AI brief where every story lists **the markets and tickers it moves** (▲ ▼ ◆), each ticker one click from its analysis, and links to its sources |
| **México** | Banxico charts (USD/MXN, Banxico vs Fed, inflation vs the 3% ± 1 target) and a live **YTD ranking of Mexican companies listed in New York** |
| **Watchlist** | S&P 500 leaders of 2026 and the live Mexico top 5 (both fixed), plus **My stocks**: any tickers you add, saved in the browser |
| **Analysis** | Chart with 50/200-day averages, risk metrics and statistical ranges; a **DCF valued four ways** (levered and unlevered, perpetuity and exit multiple) with market vs intrinsic value, reverse DCF, 5-year projection, sensitivity tables and a football field; an **Outlook** fan from 4,000 bootstrap-simulated paths with odds and key levels; a **Compare** tab vs the market (alpha, beta, capture), the sector ETF (return decomposition) and a peer comps table; **Wall Street consensus**; and an AI **Buy / Hold / Sell lean** with bull/base/bear cases |
| **Methodology** | Every formula and source, plus a live data-health check |

## Valuation approach

- **Drivers** (all adjustable): tax rate, revenue/earnings growth (years 1–5), WACC, cost of equity, perpetual growth,
  EV/EBITDA exit multiple, year-5 EBITDA margin, capex and D&A as % of revenue, working capital per dollar of new revenue.
  Defaults come from the latest 10-K (SEC XBRL) and market data.
- **Unlevered DCF**: FCFF = EBIT(1−t) + D&A − capex − ΔNWC, discounted at WACC (CAPM cost of equity + after-tax cost of debt,
  market-value weights); EV − net debt = equity.
- **Levered DCF**: FCFE = FCFF − interest(1−t) + net borrowing, discounted at the cost of equity.
- **Terminal value**: Gordon growth or EV/EBITDA exit, each cross-checked against the other (implied multiple / implied growth).
- **Reverse DCF** solves for the growth the current price implies.
- Mexican ADRs file 20-Fs in IFRS and pesos, with ADR ratios, so the automatic DCF covers US filers; ADRs get multiples and consensus.

## Being honest about the data

- Free plans don't carry exact index levels or BMV prices, so the app uses ETFs (SPY, QQQ, DIA, IWM, EWW) and NYSE-listed ADRs, and labels them as such.
- Every figure carries a freshness badge: live, delayed, last close, or daily/monthly for official series.
- Statistical ranges are labeled as ranges, not forecasts. The AI only sees data the app fetched, and stories that cite nothing are dropped.

## Stack

Python · Streamlit · pandas · NumPy · Plotly · Finnhub · Twelve Data · FRED · Banxico SIE · SEC EDGAR · CoinGecko · Gemini · RSS.
Hosting and every data source run on free tiers.

## Run it locally

```bash
pip install -r requirements.txt
AMB_DEMO=1 streamlit run app.py   # synthetic data, no keys needed
streamlit run app.py              # real data: put your keys in .streamlit/secrets.toml (see secrets.example.toml)
pytest -q                         # finance math and SEC parsing tests
```

*Personal project. Not investment advice.*
