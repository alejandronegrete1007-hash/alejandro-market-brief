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
    ("FRED", "Primary source", "US 10-year Treasury yield, Fed funds target", "Free key, personal use"),
    ("SEC EDGAR", "Primary source", "10-K financials (XBRL company facts) for the DCF", "Free, 10 requests/sec"),
    ("CoinGecko", "Data provider", "Bitcoin price", "Free public endpoint"),
    ("CNBC, MarketWatch, WSJ, Fed, El Financiero, Google News", "News (RSS)", "Headlines and summaries, always linked to the article",
     "Public feeds"),
    ("Google Gemini", "AI", "Daily brief and the per-stock take, written only from the data above", "Free tier"),
]


def render():
    T.show('<div class="amb-hero"><div><div class="amb-kicker">Methodology</div><h1>How the numbers are made</h1>'
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

**DCF.** Free cash flow = operating cash flow − capital expenditures, from the 10-K. Five years at the chosen growth rate,
five more fading linearly to terminal growth, then a Gordon terminal value. Everything is discounted at the WACC
(default: CAPM, risk-free + beta × 5% equity premium, kept between 7% and 14%). Equity = enterprise value − net debt;
divided by shares outstanding. *Undervalued* / *Overvalued* means the base value is more than 10% above / below the price.
Bear = half the growth and +1 pt WACC; bull = 1.5× growth and −1 pt WACC.

**Reverse DCF.** Solves for the growth rate that makes the DCF value equal today's price: what the market is "paying for".

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
            ("Banxico series", lambda: " | ".join(f"{k}: {v['value']} · {v['title'][:60]}" for k, v in mexico.indicators().items())),
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
