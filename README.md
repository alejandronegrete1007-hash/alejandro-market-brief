# Alejandro Market Brief

A personal markets dashboard covering **two markets, Wall Street and Mexico**, built in Python.
Every morning it answers three questions in about five minutes: what moved, why, and what my stocks are worth.

**Live app:** https://alejandro-market-brief.streamlit.app

## What it does

| Page | What you get |
|---|---|
| **Today** | US indices (via ETFs), gold, oil, Bitcoin and the 10Y yield; the peso (Banxico FIX), Banxico's rate, CETES, TIIE, inflation and the real policy rate; an AI-written brief with a Wall Street and a Mexico section, where every story links to its sources |
| **México** | Banxico charts (USD/MXN, Banxico vs Fed policy rates, inflation vs the 3% ± 1 target) and a live **YTD ranking of Mexican companies listed in New York** |
| **Watchlist** | Two editable lists of five: S&P 500 names (starting with 2026's biggest gainers: MRNA, SNDK, DELL, MU, MPC) and Mexican ADRs (following the live YTD top 5) |
| **Analysis** | Price chart with 50/200-day averages, volatility, max drawdown, beta, Sharpe, statistical price ranges, a **DCF with reverse DCF, scenarios, sensitivity table and football-field chart**, multiples, news and an AI "take" with bull / base / bear cases |
| **Methodology** | Every formula and source, plus a live data-health check |

## Valuation approach

- **Free cash flow** = operating cash flow − capex, read from the company's 10-K (SEC XBRL), by fiscal year.
- **Two-stage DCF**: 5 years at the chosen growth rate, 5 years fading to terminal growth, Gordon terminal value.
- **Discount rate** defaults to CAPM (10Y Treasury + beta × 5% ERP, bounded 7–14%).
- **Reverse DCF** solves for the growth rate the current price implies, often the most useful single number.
- **Verdict**: undervalued / overvalued when the base value is more than 10% away from the price.
- Mexican ADRs file 20-Fs in IFRS and pesos, with ADR ratios, so the automatic DCF covers US filers; ADRs get multiples.

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
