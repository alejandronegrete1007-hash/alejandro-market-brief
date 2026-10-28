# Alejandro Market Brief

A personal markets dashboard covering **two markets, Wall Street and Mexico**, built in Python.
Every morning it answers three questions in about five minutes: what moved, why, and what my stocks are worth.

**Live app:** https://alejandro-market-brief.streamlit.app

## What it does

| Page | What you get |
|---|---|
| **Today** | Clickable cards for US indices (via ETFs), gold, oil, Bitcoin, the 10Y yield, the **Treasury yield curve** (with 10Y−2Y and 10Y−3M spreads), **sector performance**, the peso (Banxico FIX), Banxico's rate, inflation, CETES, TIIE and the real policy rate. An AI brief where every story lists **the markets and tickers it moves** (▲ ▼ ◆), each ticker one click from its analysis, and links to its sources |
| **News** | Headlines by market and by **sector** (keyword-tagged, with an AI tone and one-line read per sector and the sector ETF's move), plus company news for the stocks you hold and follow |
| **México** | Banxico charts (USD/MXN, Banxico vs Fed, inflation vs the 3% ± 1 target) and a live **YTD ranking of Mexican companies listed in New York** |
| **Watchlist** | S&P 500 leaders of 2026 and the live Mexico top 5 (both fixed), plus **My stocks** saved in the browser |
| **Portfolio** | Add a position with just the stock, the date and the shares (the buy price is that day's close); a broker-style **P&L** per purchase vs the S&P 500 over the same period, time-weighted return, contribution to P&L, allocation, VaR and beta of the holdings, an AI portfolio review and a **PDF report**; the **track record of your research calls** (call alpha vs the S&P 500, hit rate) and a **portfolio lab**: Markowitz efficient frontier with CAPM expected returns, Ledoit-Wolf constant-correlation covariance, tangency and minimum-variance portfolios, your own portfolio and the correlation matrix |
| **Analysis** | Seven tabs for any US-listed stock: **Chart & risk** (moving averages, drawdown, historical VaR / expected shortfall vs a normal model, skew and kurtosis) · **Valuation** (cost of capital built step by step, a DCF valued four ways, bear/base/bull scenarios with probabilities, peers' multiples, football field, sensitivity) · **Financials** (horizontal and vertical analysis, liquidity, leverage, activity and profitability ratios, DuPont, earnings-quality checks, **EVA** and ROIC vs WACC) · **Outlook** (4,000 bootstrap-simulated paths) · **Compare** (vs market, sector and competitors) · **Research note** (Wall Street consensus plus a one-page note: thesis, valuation, quality, scenarios, catalysts, risks; save your Buy / Hold / Sell call or download the note as a PDF) · **News** |
| **Methodology** | Every formula and source, plus a live data-health check |

A search box in the header finds any US-listed company or ADR by name or ticker (press `/`), and every card, ticker-tape
item and table row opens its analysis.

## Valuation approach

- **Cost of capital**: CAPM with the 10-year Treasury, Blume-adjusted beta and an adjustable equity risk premium
  (default 5%; 4.45% Damodaran, 4.5–5.5% surveys); cost of debt from interest expense / debt; market-value weights.
- **Drivers** (all adjustable): tax rate, revenue/earnings growth (years 1–5), WACC, cost of equity, perpetual growth,
  EV/EBITDA exit multiple, year-5 EBITDA margin, capex and D&A as % of revenue, working capital per dollar of new revenue.
  Defaults come from the latest 10-K (SEC XBRL), the peer group and market data: growth = 5-year CAGR capped at 15%,
  year-5 margin = the company's 5-year average (mean reversion), exit multiple = the lower of today's own and the peer median EV/EBITDA (no assumed re-rating),
  working capital = (receivables + inventory − payables) / revenue.
- **Unlevered DCF**: FCFF = EBIT(1−t) + D&A − capex − ΔNWC, discounted at WACC; EV − net debt = equity.
- **Levered DCF**: FCFE = FCFF − interest(1−t) + net borrowing, discounted at the cost of equity.
- **Terminal value**: Gordon growth on a **normalized year 6** (working capital and borrowing at the perpetual rate, capex
  settling near D&A) or an EV/EBITDA exit, each cross-checked against the other (implied multiple / implied growth).
- **Scenarios**: bear / base / bull with editable probabilities; intrinsic value is the probability-weighted average.
- **Reverse DCF** solves for the growth the current price implies.
- Mexican ADRs file 20-Fs in IFRS and pesos, with ADR ratios, so the automatic DCF covers US filers; ADRs get multiples and consensus.
- The SEC extraction is checked against filed numbers in CI (`scripts/check_filings.py`); e.g. Micron FY2026: revenue
  $133.19B, EBITDA $108.8B, total debt $5.18B, matching the 10-K.

## Being honest about the data

- Free plans don't carry exact index levels or BMV prices, so the app uses ETFs (SPY, QQQ, DIA, IWM, EWW) and NYSE-listed ADRs, and labels them as such.
- Every figure carries a freshness badge: live, delayed, last close, or daily/monthly for official series.
- Statistical ranges are labeled as ranges, not forecasts. The AI only sees data the app fetched, and stories that cite nothing are dropped.

## Stack

Python · Streamlit · pandas · NumPy · SciPy · Plotly · Finnhub · Twelve Data · FRED · Banxico SIE · SEC EDGAR · CoinGecko · Gemini · RSS.
Hosting and every data source run on free tiers. A GitHub Actions job visits every page every two hours
(6:00–24:00 Mexico City) with a headless browser, so the app is awake and its data cached when someone opens it.

## Run it locally

```bash
pip install -r requirements.txt
AMB_DEMO=1 streamlit run app.py   # synthetic data, no keys needed
streamlit run app.py              # real data: put your keys in .streamlit/secrets.toml (see secrets.example.toml)
pytest -q                         # DCF, EVA (incl. the seminar's EVA problem), ratios, VaR, P&L and TWR, Markowitz, Ledoit-Wolf
```

*Personal project. Not investment advice.*
