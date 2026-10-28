"""Methodology: where every number comes from, plus a live check of each data source."""
from __future__ import annotations

import time

import streamlit as st

import ai
import mexico
import sources as src
import theme as T

SOURCES = [
    ("Finnhub", "Data provider", "Quotes, market status, company profile, multiples, company & market news, earnings dates",
     "60 calls/min (free)"),
    ("Twelve Data", "Data provider", "Daily price history: charts, YTD base, volatility, beta", "8 calls/min, 800/day (free)"),
    ("Banxico SIE", "Primary source", "USD/MXN FIX, target rate, TIIE, CETES, inflation (INPC)", "Free token, official data"),
    ("FRED", "Primary source", "Treasury yield curve (1M to 30Y), Fed funds target", "Free key, personal use"),
    ("SEC EDGAR", "Primary source", "10-K financials (XBRL company facts): DCF, ratios, EVA", "Free, 10 requests/sec"),
    ("CoinGecko", "Data provider", "Bitcoin price", "Free public endpoint"),
    ("CNBC, MarketWatch, WSJ, Fed, El Financiero, Google News", "News (RSS)", "Headlines and summaries, always linked to the article",
     "Public feeds"),
    ("Google Gemini", "AI", "Daily brief and the research notes, written only from the data above", "Free tier"),
]


def render():
    T.show('<div class="amb-hero"><div><h1>How the numbers are made</h1>'
           '<div class="sub">Every figure is either fetched, calculated from fetched data, or written by the AI from both. '
           'The app labels which is which.</div></div></div>')

    T.section("Sources")
    rows = "".join(f'<tr><td><b style="color:var(--text)">{T.esc(a)}</b></td><td>{T.esc(b)}</td><td>{T.esc(c)}</td>'
                   f'<td style="color:var(--muted);font-family:var(--mono);font-size:.78rem">{T.esc(d)}</td></tr>' for a, b, c, d in SOURCES)
    T.show(f'<div class="amb-wrap"><table class="amb-lb"><thead><tr><th>Source</th><th>Type</th><th>Used for</th><th>Limits</th></tr>'
           f'</thead><tbody>{rows}</tbody></table></div>')

    T.section("Methods")
    st.markdown("""
**Index levels.** Exact S&P 500, Nasdaq, Dow and IPC levels aren't in any free plan, so the app tracks the ETFs that follow
them (SPY, QQQ, DIA, IWM, and EWW for Mexico). Their daily % change is almost identical to the index.

**Freshness badges.** *Live* = a trade in the last 5 minutes while the market is open. *Delay* = older than that.
*Close* = the market is shut and the figure is the last close. *Daily / monthly* = official series published once a period.

**YTD return.** Latest price divided by the last close of the previous year, minus one. The Mexico ranking uses the same
formula for every ADR, with prices in dollars, so it reflects both the stock and the peso.

**Volatility.** Standard deviation of daily log returns over the last 252 sessions, times √252.

**Max drawdown.** The worst fall from a previous high within the last year.

**Beta.** Covariance of the stock's weekly returns with SPY's, divided by SPY's variance, over two years.

**Sharpe ratio.** One-year annualized return minus the 10-year Treasury yield, divided by volatility.

**Statistical ranges.** price × e^(±z·σ·√(days/252)) with z = 1 (≈68%) and 1.96 (≈95%), zero drift. They describe how
far the stock usually moves, not where it is going.

**Cost of capital.** Cost of equity by CAPM: 10-year Treasury + adjusted beta × equity risk premium (default 5%; the
course guides cite 4.45% from Damodaran and 4.5–5.5% from valuation surveys; a Mexican company valued in dollars adds about
2.8–3.1% of country risk). Adjusted beta = 0.67 × measured beta + 0.33 (Blume). Cost of debt = interest expense / debt,
after tax. WACC weights equity and debt at market value.

**DCF: four valuations.** A 5-year model driven by revenue. Revenue grows at the chosen rate (default: 5-year CAGR, capped
at 15%); the EBITDA margin moves in a straight line from last year's level to your year-5 target (default: the company's own
5-year average, because peak and trough margins revert); D&A and capex are a % of revenue; working capital absorbs
(receivables + inventory − payables) / revenue of each year's new revenue, from the last 10-K; taxes apply to EBIT.

- **Unlevered (FCFF at WACC):** FCFF = EBIT × (1 − tax) + D&A − capex − Δ working capital. Enterprise value − net debt = equity.
- **Levered (FCFE at cost of equity):** FCFE = FCFF − interest × (1 − tax) + net new borrowing (debt grows with revenue).
  Cash on hand is added.
- **Terminal value:** *perpetual growth* values a normalized year 6 (revenue, working capital and borrowing grow at the
  perpetual rate; capex settles at no more than 15% above D&A) as a growing perpetuity, or an *EV/EBITDA exit multiple*
  sells the business at year 5 (default multiple: the lower of today's own EV/EBITDA and the peer-group median, kept
  between 4x and 25x, so the model never assumes a re-rating). Each implies the other as a check.
- **Scenarios:** bear and bull move growth ±5 pts, the year-5 margin ±15%, the exit multiple ±20% and discount rates ∓1 pt.
  Intrinsic value is the probability-weighted average (25 / 50 / 25 by default) of each scenario's four-method average.
  *Undervalued* / *Overvalued* = more than 10% above / below the price.
- **Peers' multiples:** the peers' 25th–75th percentile P/E, P/S and EV/EBITDA applied to this company, in the football field.

**Reverse DCF.** Solves for the 5-year growth rate that makes the unlevered perpetuity value equal today's price.

**Financial statement analysis.** From the 10-K: horizontal analysis (growth year over year), vertical analysis (each line
as % of revenue), liquidity (current and quick ratios), leverage (debt / equity, net debt / EBITDA, interest coverage),
activity (asset turnover, days sales outstanding, days inventory), profitability (ROA, ROE on average balances) and the
DuPont split ROE = net margin × asset turnover × equity multiplier. Earnings-quality checks flag operating cash flow below
net income, receivables growing faster than sales and thin interest coverage.

**Economic value added.** EVA = NOPAT − WACC × capital employed, with NOPAT = EBIT × (1 − tax) and capital employed =
interest-bearing debt + equity (total assets minus non-interest-bearing current liabilities), averaged over the year.
Positive EVA means the return on capital beats its cost.

**Tail risk.** Historical 1-day Value at Risk (the loss not exceeded on 95% or 99% of days) and expected shortfall (the
average loss beyond it) from two years of real daily returns, compared with what a normal distribution would say, plus
skewness and excess kurtosis. Real returns have fatter tails than the bell curve.

**Portfolio and P&L.** Positions (ticker, shares, average cost, date) are marked to market with live quotes: market value,
daily P&L (shares × today's change), unrealized P&L (market value − cost basis) and weight in net liquidation value
(positions + cash). Performance is the time-weighted return: each purchase is new money on its date, so
r_t = (V_t − F_t) / V_(t−1) − 1, compared with SPY over the same days. Risk applies today's weights to two years of daily
returns (historical simulation): beta, annualized volatility, 1-day VaR and expected shortfall in dollars, and the effective
number of positions (1 / Σw²).

**Portfolio lab.** Markowitz mean-variance optimization, long-only and fully invested, with a cap per stock. Expected
returns from CAPM (the same cost of equity as the DCF); risk from the covariance of two years of weekly returns, annualized
and shrunk with Ledoit-Wolf (2004) toward a constant-correlation matrix, which keeps each stock's variance and pulls noisy
correlations toward their average (checked against PyPortfolioOpt in the tests). Shows the efficient frontier, the
minimum-variance and maximum-Sharpe (tangency) portfolios, your own portfolio, the capital market line and the
correlation matrix. The tangency search starts from several points because the Sharpe ratio is not convex.

**News.** Headlines from the general and sector RSS feeds and Finnhub, last 36 hours, near-duplicates removed, assigned to
sectors by keywords in English and Spanish. Gemini writes one line and a tone per sector only from that sector's headlines.
"My stocks" pulls Finnhub company news for your positions, My stocks and the 2026 leaders.

**Outlook (price simulation).** 4,000 six-month paths. Each simulated day replays a randomly chosen real daily move
from the last two years (a bootstrap), re-centred to the drift you pick: neutral (0%), market average (+8% a year) or the
recent trend (capped at ±30%). Because the moves are real, crash days are included, which a normal-distribution model
understates. The fan shows the 5/25/50/75/95th percentile paths; probabilities are the share of paths that do something
(end higher, fall 20% at some point, reach the DCF value). Odds of a model, not a forecast.

**Compare.** All lines are rebased to 100 at the start of the window. Beta, correlation and up/down capture use two
years of weekly returns; alpha is Jensen's alpha over one year (return beyond what beta and the market explain). The
sector split is additive: market return + sector over market + stock over sector = the stock's return. Competitors come
from Finnhub's peer list; the comps table colours the stock's cell green when it beats the peer median (a cheaper
multiple, or higher growth, margin, return or analyst score).

**Analyst consensus.** Monthly buy / hold / sell counts from the analysts covering the stock (Finnhub recommendation
trends). Score: strong buy = 5 … strong sell = 1.

**Research note.** Gemini writes the thesis, scenarios, risks, catalysts and a Buy / Hold / Sell lean only from the
numbers of every tab (valuation with your assumptions, financial analysis, EVA, risk, comparison and consensus), and must
say what would change its mind. The call is yours: you can save it, and the Portfolio page tracks its return against the S&P 500
from that day (price and S&P 500 level are recorded when you save). The note downloads as a printable page.

**DCF for Mexican ADRs.** Not automatic: they file a 20-F in IFRS and pesos, and one ADR equals several local shares.
Their multiples (Finnhub) are still shown.

**AI.** Gemini only receives the numbers and headlines shown in the app and must cite the headlines behind each story.
Stories citing nothing real are dropped. It is told never to invent figures, targets or probabilities.
""")

    T.section("Data health", "checks each source live")
    if st.button("Run the check", type="primary"):
        checks = [
            ("Finnhub quote (SPY)", lambda: f"{src.quote('SPY')['price']:.2f}"),
            ("Twelve Data history (SPY)", lambda: f"{len(src.history('SPY'))} sessions"),
            ("FRED 10Y", lambda: f"{src.fred('DGS10').iloc[-1]:.2f}%"),
        ] + [
            (f"Banxico {key} ({sid})",
             lambda sid=sid: " | ".join(f"{v['value']} on {v['date']} · {v['title'][:70]}"
                                        for v in src._bx_parse_latest(src._bx(f"/{sid}/datos/oportuno")).values()) or "no data")
            for key, sid in mexico.SERIES.items()
        ] + [
            ("CoinGecko", lambda: f"{src.bitcoin()['price']:,.0f}"),
            ("SEC tickers", lambda: f"{len(src.sec_ciks())} companies"),
            ("US feeds", lambda: f"{len(src.feeds('US')[0])} items, failed: {src.feeds('US')[1] or 'none'}"),
            ("Mexico feeds", lambda: f"{len(src.feeds('MX')[0])} items, failed: {src.feeds('MX')[1] or 'none'}"),
            ("Gemini model", lambda: ai.pick_model()),
        ]
        for name, fn in checks:
            t0 = time.time()
            try:
                out = fn()
                st.success(f"**{name}** · {out} · {time.time() - t0:.1f}s")
            except Exception as e:
                st.error(f"**{name}** · {e}")
    T.footer("Built with Python, Streamlit, pandas and Plotly")
