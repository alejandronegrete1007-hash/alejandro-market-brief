"""Alejandro Market Brief - a personal dashboard for Wall Street and Mexico.

Run locally:  streamlit run app.py
Demo data:    AMB_DEMO=1 streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="Alejandro Market Brief", page_icon="assets/icon.png",
                   layout="wide", initial_sidebar_state="collapsed")

import state  # noqa: E402
import theme as T  # noqa: E402
from views import PAGES, analysis, brief, methodology, mexico_page, news, portfolio_page, search, watchlist  # noqa: E402

T.inject_css()
st.logo("assets/wordmark.svg", size="large", icon_image="assets/wordmark.svg")

PAGES.update({
    "brief": st.Page(brief.render, title="Today", url_path="today", default=True),
    "news": st.Page(news.render, title="News", url_path="news"),
    "mexico": st.Page(mexico_page.render, title="México", url_path="mexico"),
    "watchlist": st.Page(watchlist.render, title="Watchlist", url_path="watchlist"),
    "analysis": st.Page(analysis.render, title="Analysis", url_path="analysis"),
    "portfolio": st.Page(portfolio_page.render, title="Portfolio", url_path="portfolio"),
    "methodology": st.Page(methodology.render, title="Methodology", url_path="methodology"),
})
nav = st.navigation(list(PAGES.values()), position="top")
state.init()
search.render()
nav.run()
