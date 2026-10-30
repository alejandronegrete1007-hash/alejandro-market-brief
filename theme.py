"""Look and feel: design tokens, CSS, HTML components, clickable cards, formatting and the Plotly theme.

"Platinum": graphite base, charcoal panels, hairline rules and platinum text, with ONE
accent (sapphire) for interaction; muted green / red are reserved for up / down.
Two typefaces: Spectral (a serif) for titles and headline numbers, Inter Tight with
tabular figures for everything else, so columns of numbers line up. Sentence-case labels,
tight corners, one easing curve, and no motion for people who ask for less.
"""
from __future__ import annotations

import base64
import datetime as dt
import html
import math

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

C = {
    "bg": "#121417", "card": "#1A1D22", "raised": "#20242A", "line": "#2A2E35", "line2": "#383D45",
    "text": "#E4E6EA", "text2": "#A6ACB5", "muted": "#7A818C",
    "acc": "#7FA7FF", "up": "#5DB38A", "down": "#DB6461", "us": "#C9CED6", "mx": "#C8A46A", "ai": "#B39DDB",
}
C["gold"] = C["acc"]  # older name for the accent, kept so every view keeps working
SERIES = [C["acc"], C["us"], C["mx"], C["ai"], "#7FB8C9", C["text2"]]
FONT_BODY, FONT_DISPLAY = "Inter Tight", "Spectral"


def rgba(name: str, alpha: float) -> str:
    """A palette colour (or hex) with transparency, for Plotly fills."""
    h = C.get(name, name).lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{alpha})"

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Spectral:wght@400;500;600&family=Inter+Tight:wght@400;500;600;700&display=swap');

/* 1. TOKENS ------------------------------------------------------------- */
:root{
  --bg:#121417;--card:#1A1D22;--raised:#20242A;--line:#2A2E35;--line2:#383D45;
  --text:#E4E6EA;--text2:#A6ACB5;--muted:#7A818C;
  --gold:#7FA7FF;--gold-dk:#5F8BF0;--up:#5DB38A;--down:#DB6461;--us:#C9CED6;--mx:#C8A46A;--ai:#B39DDB;
  --display:'Spectral',Georgia,serif;--body:'Inter Tight',system-ui,sans-serif;--mono:'Inter Tight',system-ui,sans-serif;
  --r:6px;--r-sm:3px;--ease:cubic-bezier(.22,1,.36,1);
  --eyebrow-track:.01em;--display-track:-.005em;
}

/* 2. BASE ----------------------------------------------------------------- */
html,body,[data-testid="stAppViewContainer"],.stApp{background:var(--bg)!important;}
[data-testid="stHeader"]{background:rgba(18,20,23,.88)!important;backdrop-filter:blur(14px);border-bottom:1px solid var(--line);}
[data-testid="stSidebar"]{background:#15171B!important;border-right:1px solid var(--line);}
[data-testid="stSidebar"] a span{font-family:var(--display)!important;font-size:1.02rem;}
[data-testid="stExpandSidebarButton"]{border:1px solid var(--line2)!important;border-radius:var(--r-sm)!important;padding:2px 10px!important;}
[data-testid="stExpandSidebarButton"]::after{content:"Menu";font-family:var(--display);font-size:.85rem;margin-left:6px;color:var(--text);}
.block-container{padding-top:4.4rem!important;padding-bottom:4rem!important;max-width:1280px!important;}
html,body,p,li,span,div,label,input,button,textarea{font-family:var(--body);font-variant-numeric:tabular-nums;}
h1,h2,h3,h4{font-family:var(--display)!important;letter-spacing:var(--display-track);color:var(--text);}
p,li{color:var(--text2);}
a{color:var(--gold)!important;text-decoration:none;}
::selection{background:rgba(127,167,255,.3);}
:focus-visible{outline:2px solid var(--gold)!important;outline-offset:3px;}
.st-key-amb_store,.st-key-amb_store *{display:none!important;}

/* 3. STREAMLIT WIDGETS ----------------------------------------------------- */
[data-testid="stTabs"] button[role="tab"] p{font-family:var(--display);font-weight:600;font-size:.95rem;}
[data-testid="stTabs"] button[role="tab"]{color:var(--muted);}
[data-testid="stTabs"] button[aria-selected="true"]{color:var(--text);}
[data-testid="stTabs"] [data-baseweb="tab-highlight"]{background:var(--gold)!important;}
[data-testid="stExpander"] details{border:1px solid var(--line)!important;border-radius:var(--r)!important;background:var(--card);}
div[data-testid="stButton"] button,div[data-testid="stFormSubmitButton"] button{
  border-radius:var(--r-sm);border:1px solid var(--line2);background:var(--raised);
  font-weight:600;letter-spacing:.01em;font-size:.78rem;
  transition:transform .18s var(--ease),border-color .18s ease,background-color .18s ease;}
div[data-testid="stButton"] button:hover{border-color:var(--gold);color:var(--gold);transform:translateY(-2px);}
div[data-testid="stButton"] button:active{transform:translateY(0);}
div[data-testid="stButton"] button[kind="primary"]{background:var(--gold);border-color:var(--gold);}
div[data-testid="stButton"] button[kind="primary"],div[data-testid="stButton"] button[kind="primary"] *{color:#0E1320!important;}
div[data-testid="stButton"] button[kind="primary"]:hover{background:var(--gold-dk);border-color:var(--gold-dk);}
[data-testid="stPlotlyChart"]{border:1px solid var(--line);border-radius:var(--r);background:var(--card);overflow:hidden;}
[data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:var(--r);overflow:hidden;}
[data-testid="stSlider"] label p,[data-testid="stNumberInput"] label p,[data-testid="stSelectbox"] label p{
  font-size:.72rem!important;letter-spacing:.01em;color:var(--muted)!important;font-weight:600;}

/* 4. TYPE ------------------------------------------------------------------ */
.amb-eyebrow{font-family:var(--body);font-size:.8rem;font-weight:500;letter-spacing:var(--eyebrow-track);
  color:var(--gold);line-height:1;margin-bottom:10px;}
.amb-hero{display:flex;justify-content:space-between;align-items:flex-end;gap:24px;flex-wrap:wrap;margin:8px 0 22px;}
.amb-hero h1{font-size:clamp(2rem,4.4vw,3.3rem);line-height:1;margin:0;font-weight:500;}
.amb-hero .sub{color:var(--text2);margin-top:12px;font-size:.95rem;display:flex;gap:14px;flex-wrap:wrap;align-items:center;}
.amb-sec{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;margin:36px 0 14px;padding-bottom:10px;border-bottom:1px solid var(--line);}
.amb-sec h2{font-size:1.45rem;margin:0;font-weight:500;line-height:1.1;}
.amb-sec .right{color:var(--muted);font-size:.72rem;font-family:var(--mono);text-align:right;}
.amb-note{color:var(--muted);font-size:.78rem;line-height:1.55;margin-top:10px;}

/* 5. CLOCKS, STATUS, TAPE -------------------------------------------------- */
.amb-clocks{display:flex;gap:8px;}
.amb-clock{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:8px 12px;min-width:110px;}
.amb-clock .c-l{font-family:var(--mono);font-size:.62rem;letter-spacing:.01em;color:var(--muted);}
.amb-clock .c-v{font-family:var(--mono);font-size:1.05rem;color:var(--text);margin-top:2px;}
.amb-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;vertical-align:middle;}
.amb-dot.on{background:var(--up);box-shadow:0 0 0 4px rgba(93,179,138,.15);animation:amb-pulse 2s infinite;}
.amb-dot.off{background:var(--muted);}
@keyframes amb-pulse{50%{box-shadow:0 0 0 7px rgba(93,179,138,0);}}
.amb-tape{position:relative;overflow:hidden;border-top:1px solid var(--line);border-bottom:1px solid var(--line);background:var(--card);margin:0 0 8px;
  mask-image:linear-gradient(90deg,transparent,#000 5%,#000 95%,transparent);}
.amb-tape-track{display:flex;width:max-content;animation:amb-scroll 70s linear infinite;}
.amb-tape:hover .amb-tape-track{animation-play-state:paused;}
.amb-tape-item{display:flex;gap:10px;align-items:baseline;padding:10px 20px;border-right:1px solid var(--line);white-space:nowrap;}
.amb-tape-item[data-go]:hover{background:var(--raised);}
.amb-tape-item[data-go]:hover .t-s{color:var(--gold);}
.amb-tape-item .t-s{font-family:var(--display);font-weight:600;color:var(--text);font-size:.82rem;}
.amb-tape-item .t-p{font-family:var(--mono);color:var(--text2);font-size:.82rem;}
@keyframes amb-scroll{to{transform:translateX(-50%);}}

/* 6. GRID + TILES ---------------------------------------------------------- */
.amb-grid{display:grid;gap:12px;grid-template-columns:repeat(4,minmax(0,1fr));}
.amb-grid.g3{grid-template-columns:repeat(3,minmax(0,1fr));}
.amb-grid.g2{grid-template-columns:repeat(2,minmax(0,1fr));}
@media (max-width:1100px){.amb-grid{grid-template-columns:repeat(3,minmax(0,1fr));}}
@media (max-width:860px){.amb-grid,.amb-grid.g3{grid-template-columns:repeat(2,minmax(0,1fr));}}
.amb-tile{position:relative;display:flex;flex-direction:column;background:var(--card);border:1px solid var(--line);
  border-radius:var(--r);padding:14px 14px 12px;min-height:100%;transition:transform .3s var(--ease),border-color .2s ease,background .2s ease;}
.amb-tile .eyebrow{display:flex;justify-content:space-between;align-items:center;gap:6px;}
.amb-tile .name{font-size:.82rem;font-weight:600;color:var(--text);line-height:1.25;}
.amb-tile .tick{font-family:var(--mono);font-size:.62rem;letter-spacing:.01em;color:var(--muted);}
.amb-tile .val{font-family:var(--display);font-size:1.7rem;font-weight:500;color:var(--text);margin:10px 0 2px;letter-spacing:-.02em;line-height:1.1;}
.amb-tile .chg{margin-bottom:4px;}
.amb-tile .foot{margin-top:auto;padding-top:10px;display:flex;justify-content:space-between;align-items:center;gap:6px;
  color:var(--muted);font-size:.68rem;font-family:var(--mono);}
.amb-tile .go-hint{color:var(--gold);opacity:0;transition:opacity .2s ease;white-space:nowrap;}
.amb-tile .spark{margin:6px -2px 0;}
[data-go]{cursor:pointer;}
.amb-tile[data-go]:hover{transform:translateY(-4px);border-color:var(--line2);background:var(--raised);}
.amb-tile[data-go]:hover .go-hint{opacity:1;}
@media (hover:none){.amb-tile .go-hint{opacity:.85;}}
.amb-status{display:inline-flex;align-items:center;gap:5px;}
.amb-status i{width:6px;height:6px;border-radius:50%;display:inline-block;background:var(--muted);}
.amb-status.live i{background:var(--up);} .amb-status.delayed i{background:var(--gold);}

.amb-pill{font-family:var(--mono);font-size:.74rem;font-weight:500;padding:2px 7px;border-radius:var(--r-sm);white-space:nowrap;}
.amb-pill.up{color:var(--up);background:rgba(93,179,138,.1);}
.amb-pill.down{color:var(--down);background:rgba(219,100,97,.1);}
.amb-pill.flat{color:var(--text2);background:rgba(166,172,181,.1);}
.amb-chip{font-family:var(--mono);font-size:.6rem;font-weight:600;letter-spacing:.01em;padding:2px 6px;border-radius:var(--r-sm);white-space:nowrap;}
.amb-chip.US{color:var(--us);background:rgba(201,206,214,.1);}
.amb-chip.MX{color:var(--mx);background:rgba(200,164,106,.1);}
.amb-chip.GLOBAL{color:var(--gold);background:rgba(127,167,255,.1);}
.amb-chip.plain{color:var(--text2);border:1px solid var(--line2);}

.amb-range{margin-top:8px;}
.amb-range .lab{display:flex;justify-content:space-between;font-family:var(--mono);font-size:.6rem;letter-spacing:.01em;color:var(--muted);margin-bottom:4px;}
.amb-range .bar{position:relative;height:3px;border-radius:3px;background:var(--line2);}
.amb-range .fill{position:absolute;inset:0;border-radius:3px;background:linear-gradient(90deg,var(--down),var(--gold),var(--up));opacity:.5;}
.amb-range .mark{position:absolute;top:-4px;width:2px;height:11px;background:var(--text);border-radius:2px;}
.amb-range .ends{display:flex;justify-content:space-between;font-family:var(--mono);font-size:.66rem;color:var(--text2);margin-top:4px;}

/* 7. BRIEF ------------------------------------------------------------------ */
.amb-lead{font-family:var(--display);font-size:clamp(1.3rem,2.6vw,1.9rem);line-height:1.25;color:var(--text);margin:4px 0 16px;font-weight:500;}
.amb-lead span{color:var(--gold);}
.amb-take{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:18px 20px;}
.amb-take .h{display:flex;gap:8px;align-items:center;margin-bottom:8px;font-family:var(--display);font-weight:600;color:var(--text);}
.amb-take p{margin:0;line-height:1.65;color:var(--text2);font-size:.95rem;}
.amb-story{display:flex;flex-direction:column;gap:10px;background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:18px;}
.amb-story .top{display:flex;gap:8px;align-items:center;}
.amb-story .rank{font-family:var(--mono);color:var(--muted);font-size:.72rem;}
.amb-story h3{font-size:1.05rem;margin:0;line-height:1.3;font-weight:600;}
.amb-story .row{font-size:.9rem;line-height:1.55;color:var(--text2);}
.amb-story .row b{display:block;color:var(--muted);font-weight:600;font-size:.62rem;letter-spacing:var(--eyebrow-track);font-family:var(--mono);margin-bottom:2px;}
.amb-impact{border-top:1px solid var(--line);padding-top:10px;display:flex;flex-direction:column;gap:6px;}
.amb-impact .mk{display:flex;flex-wrap:wrap;gap:6px;}
.amb-tk{display:inline-flex;align-items:center;gap:6px;font-family:var(--mono);font-size:.74rem;padding:4px 8px;border-radius:var(--r-sm);
  border:1px solid var(--line2);background:var(--raised);color:var(--text);transition:border-color .15s ease,transform .18s var(--ease);}
.amb-tk[data-go]:hover{border-color:var(--gold);transform:translateY(-1px);}
.amb-tk .ar.up{color:var(--up);} .amb-tk .ar.down{color:var(--down);} .amb-tk .ar.mixed{color:var(--gold);}
.amb-tk .why{font-family:var(--body);color:var(--muted);font-size:.72rem;}
.amb-srcs{display:flex;flex-wrap:wrap;gap:6px;margin-top:auto;padding-top:4px;}
.amb-src{font-family:var(--mono);font-size:.64rem;color:var(--text2)!important;border:1px solid var(--line2);border-radius:var(--r-sm);padding:3px 7px;}
.amb-src:hover{border-color:var(--gold);color:var(--gold)!important;}

/* 8. LISTS, TABLES ----------------------------------------------------------- */
.amb-news{display:flex;flex-direction:column;}
.amb-news a.n{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;padding:12px 2px;border-bottom:1px solid var(--line);color:var(--text)!important;}
.amb-news a.n:hover .t{color:var(--gold);}
.amb-news .t{font-weight:500;line-height:1.35;color:var(--text);}
.amb-news .m{grid-column:2;font-family:var(--mono);font-size:.66rem;color:var(--muted);}
.amb-rows{display:flex;flex-direction:column;border:1px solid var(--line);border-radius:var(--r);overflow:hidden;background:var(--card);}
.amb-row{display:grid;grid-template-columns:28px 1fr auto auto;gap:4px 14px;align-items:center;padding:12px 14px;border-bottom:1px solid var(--line);
  transition:background .2s ease;}
.amb-row:last-child{border-bottom:none;}
.amb-row[data-go]:hover{background:var(--raised);}
.amb-row .rk{font-family:var(--mono);color:var(--muted);font-size:.75rem;}
.amb-row.top .rk{color:var(--gold);}
.amb-row .s{font-family:var(--display);font-weight:600;color:var(--text);}
.amb-row .n{font-size:.74rem;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.amb-row .p{font-family:var(--mono);color:var(--text);text-align:right;font-size:.88rem;}
.amb-row .y{font-family:var(--mono);text-align:right;font-size:.88rem;min-width:70px;}
.amb-row .bar{grid-column:2/-1;height:3px;border-radius:3px;background:var(--line);overflow:hidden;}
.amb-row .bar i{display:block;height:100%;background:var(--up);opacity:.7;}
.amb-row .bar i.neg{background:var(--down);}
.amb-th{font-family:var(--mono);font-size:.62rem;letter-spacing:var(--eyebrow-track);color:var(--muted);}
.amb-table{width:100%;border-collapse:collapse;}
.amb-table th{font-family:var(--mono);font-size:.62rem;letter-spacing:.01em;color:var(--muted);font-weight:500;text-align:right;padding:10px;border-bottom:1px solid var(--line2);}
.amb-table th:first-child,.amb-table td:first-child{text-align:left;}
.amb-table td{padding:10px;border-bottom:1px solid var(--line);font-family:var(--mono);font-size:.84rem;color:var(--text);text-align:right;}
.amb-table tr.sub td{color:var(--muted);font-size:.76rem;}
.amb-table tr.hl td{color:var(--gold);font-weight:600;}
.amb-wrap{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:4px 12px;overflow-x:auto;}

/* 9. STOCK CARDS ------------------------------------------------------------- */
.amb-stock{display:flex;flex-direction:column;background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:16px;
  transition:transform .3s var(--ease),border-color .2s ease;min-height:100%;}
.amb-stock[data-go]:hover{transform:translateY(-4px);border-color:var(--line2);}
.amb-stock[data-go]:hover .go-hint{opacity:1;}
.amb-stock .hd{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;}
.amb-stock .sym{font-family:var(--display);font-size:1.25rem;font-weight:600;color:var(--text);line-height:1;}
.amb-stock .nm{color:var(--muted);font-size:.76rem;margin-top:4px;}
.amb-stock .px{font-family:var(--display);font-size:1.3rem;color:var(--text);text-align:right;}
.amb-stock .stats{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:12px;}
.amb-stock .st{border:1px solid var(--line);border-radius:var(--r-sm);padding:7px 8px;}
.amb-stock .st .k{font-size:.58rem;font-family:var(--mono);letter-spacing:.01em;color:var(--muted);}
.amb-stock .st .v{font-family:var(--mono);color:var(--text);font-size:.86rem;margin-top:2px;}
.amb-stock .foot{margin-top:auto;padding-top:12px;display:flex;justify-content:space-between;font-family:var(--mono);font-size:.66rem;color:var(--muted);}
.amb-stock .go-hint{color:var(--gold);opacity:0;transition:opacity .2s ease;}
@media (hover:none){.amb-stock .go-hint{opacity:.85;}}
.amb-logo{width:34px;height:34px;border-radius:8px;background:#fff;object-fit:contain;padding:3px;}
.amb-logo.ph{display:flex;align-items:center;justify-content:center;background:var(--line2);color:var(--text);font-family:var(--display);font-weight:600;padding:0;}

/* 10. KEY-VALUE, VERDICT, TAGS ------------------------------------------------ */
.amb-kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;}
.amb-kv .c{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:12px 14px;}
.amb-kv .k{font-size:.62rem;font-family:var(--mono);letter-spacing:.01em;color:var(--muted);}
.amb-kv .v{font-family:var(--display);font-size:1.3rem;color:var(--text);margin-top:6px;}
.amb-kv .h{font-size:.7rem;color:var(--muted);margin-top:4px;line-height:1.35;}
.amb-verdict{border-radius:var(--r);padding:20px 22px;border:1px solid var(--line);background:var(--card);display:flex;gap:24px;flex-wrap:wrap;align-items:center;justify-content:space-between;}
.amb-verdict .big{font-family:var(--display);font-size:2rem;font-weight:500;line-height:1;}
.amb-verdict.under{border-color:rgba(93,179,138,.35);background:linear-gradient(120deg,rgba(93,179,138,.07),var(--card) 55%);}
.amb-verdict.over{border-color:rgba(219,100,97,.35);background:linear-gradient(120deg,rgba(219,100,97,.07),var(--card) 55%);}
.amb-verdict.fair{border-color:rgba(127,167,255,.35);background:linear-gradient(120deg,rgba(127,167,255,.07),var(--card) 55%);}
.amb-verdict .nums{display:flex;gap:26px;flex-wrap:wrap;}
.amb-verdict .nums .k{font-family:var(--mono);font-size:.6rem;letter-spacing:.01em;color:var(--muted);}
.amb-verdict .nums .v{font-family:var(--display);font-size:1.45rem;color:var(--text);margin-top:4px;}
.amb-tag{font-family:var(--mono);font-size:.6rem;letter-spacing:.01em;padding:2px 6px;border-radius:var(--r-sm);margin-right:6px;}
.amb-tag.data{color:var(--us);background:rgba(201,206,214,.1);}
.amb-tag.calc{color:var(--gold);background:rgba(127,167,255,.1);}
.amb-tag.ai{color:var(--ai);background:rgba(179,157,219,.1);}
.amb-bars{display:flex;height:10px;border-radius:3px;overflow:hidden;margin:10px 0 6px;}
.amb-bars i{display:block;height:100%;}
.amb-empty{border:1px dashed var(--line2);border-radius:var(--r);padding:20px;color:var(--muted);}
.amb-foot{margin-top:48px;padding-top:16px;border-top:1px solid var(--line);display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;color:var(--muted);font-size:.7rem;font-family:var(--mono);}

/* 10b. FINANCIALS, RESEARCH NOTE ------------------------------------------------ */
.amb-checks{display:flex;flex-direction:column;gap:8px;}
.amb-check{display:flex;gap:10px;align-items:flex-start;background:var(--card);border:1px solid var(--line);border-radius:var(--r);
  padding:11px 14px;color:var(--text2);font-size:.9rem;line-height:1.45;}
.amb-check i{flex:none;width:8px;height:8px;border-radius:50%;margin-top:6px;background:var(--up);}
.amb-check.watch i{background:var(--down);}
.amb-check.watch{border-color:rgba(219,100,97,.35);}
.amb-table tr.grp td{font-family:var(--display);font-size:.98rem;color:var(--text);text-align:left;padding-top:18px;border-bottom:1px solid var(--line2);}
.amb-table.fin td:first-child{color:var(--text2);}
.amb-note-card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);overflow:hidden;}
.amb-note-head{display:grid;grid-template-columns:minmax(150px,auto) 1fr;gap:24px;align-items:center;padding:22px 24px;border-bottom:1px solid var(--line);}
.amb-note-head .call{font-family:var(--display);font-size:2.3rem;font-weight:500;line-height:1;margin-top:6px;}
.amb-note-head .one{margin:0;font-family:var(--display);font-size:1.25rem;line-height:1.4;color:var(--text);}
.amb-note-body{display:grid;grid-template-columns:1fr 1fr;gap:28px;padding:20px 24px 22px;}
.amb-note-body h4{font-family:var(--display);font-weight:500;font-size:1.05rem;margin:0 0 6px;color:var(--text);}
.amb-note-body h4:not(:first-child){margin-top:16px;}
.amb-note-body p,.amb-note-body li{color:var(--text2);line-height:1.6;font-size:.93rem;margin:0;}
.amb-note-body ol{margin:0;padding-left:20px;display:flex;flex-direction:column;gap:8px;}
.amb-ul{margin:0;padding-left:18px;color:var(--text2);line-height:1.6;font-size:.93rem;}
@media (max-width:860px){.amb-note-head,.amb-note-body{grid-template-columns:1fr;gap:12px;}}

/* 10b2. NEWS, P&L ------------------------------------------------------------- */
.amb-sector{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:14px 16px;min-height:100%;
  transition:border-color .2s ease,background .2s ease;}
.amb-sector[data-go]:hover{border-color:var(--line2);background:var(--raised);}
.amb-sector.sel{border-color:var(--gold);}
.amb-sector .top{display:flex;justify-content:space-between;align-items:center;gap:8px;}
.amb-sector .nm{font-family:var(--display);font-size:1.12rem;color:var(--text);}
.amb-sector .meta{display:flex;gap:8px;align-items:center;margin-top:6px;color:var(--muted);font-size:.74rem;}
.amb-sector p{margin:8px 0 0;color:var(--text2);font-size:.86rem;line-height:1.5;}
.amb-sector .latest{margin-top:8px;padding-top:8px;border-top:1px solid var(--line);color:var(--text2);font-size:.8rem;line-height:1.45;}
.amb-sector .latest b{color:var(--muted);font-weight:500;margin-right:4px;}
.amb-sector .wait{display:flex;align-items:center;gap:8px;margin-top:8px;color:var(--muted);font-size:.8rem;}
.amb-spin{width:13px;height:13px;border-radius:50%;border:2px solid var(--line2);border-top-color:var(--acc);
  animation:amb-spin .8s linear infinite;flex:none;}
@keyframes amb-spin{to{transform:rotate(360deg);}}
.amb-nlist{display:flex;flex-direction:column;}
.amb-nrow{padding:13px 2px;border-bottom:1px solid var(--line);}
.amb-nrow a{color:var(--text)!important;font-weight:500;line-height:1.4;}
.amb-nrow a:hover{color:var(--gold)!important;}
.amb-nrow .s{color:var(--text2);font-size:.84rem;line-height:1.5;margin-top:4px;}
.amb-nrow .m{color:var(--muted);font-size:.72rem;margin-top:5px;}
.amb-nrow .amb-tk{margin-right:6px;padding:2px 7px;cursor:pointer;}
.amb-sub-name{display:block;color:var(--muted);font-size:.72rem;font-weight:400;margin-top:1px;}
.amb-table.pnl td{white-space:nowrap;}
.amb-x{display:inline-flex;width:24px;height:24px;align-items:center;justify-content:center;border-radius:var(--r-sm);
  color:var(--muted);border:1px solid var(--line2);cursor:pointer;font-size:.72rem;}
.amb-x:hover{color:var(--down);border-color:var(--down);}
.amb-picked{height:40px;display:flex;align-items:center;gap:8px;padding:0 12px;border:1px dashed var(--line2);border-radius:var(--r);
  color:var(--muted);font-size:.86rem;white-space:nowrap;overflow:hidden;}
.amb-picked b{color:var(--text);}
.st-key-pf_pick .amb-search input{height:40px;}
.amb-table.pnl th:first-child,.amb-table.pnl td:first-child{position:sticky;left:0;background:var(--card);z-index:1;}
.amb-swipe{display:none;color:var(--muted);font-size:.72rem;margin:6px 0 0;}
@media (max-width:640px){
  .amb-table.pnl th:nth-child(3),.amb-table.pnl td:nth-child(3),.amb-table.pnl th:nth-child(6),.amb-table.pnl td:nth-child(6){display:none;}
  .amb-table.pnl td,.amb-table.pnl th{padding:9px 7px;font-size:.8rem;}
  .amb-swipe{display:block;}
  .amb-lb thead{display:none;}
  .amb-lb tr{display:block;padding:10px 0;border-bottom:1px solid var(--line);}
  .amb-lb td{display:block;border:none!important;padding:2px 0!important;text-align:left!important;}
}

/* 10c. HEADER SEARCH ---------------------------------------------------------- */
.st-key-amb_search{position:fixed!important;top:12px;right:190px;width:320px!important;z-index:999995;}
.amb-search{position:relative;}
.amb-search svg{position:absolute;left:11px;top:10px;width:16px;height:16px;fill:none;stroke:var(--muted);stroke-width:1.6;pointer-events:none;}
.amb-search input{width:100%;height:36px;box-sizing:border-box;padding:0 34px 0 34px;border-radius:var(--r);border:1px solid var(--line2);
  background:var(--card);color:var(--text);font:400 .9rem var(--body);outline:none;caret-color:var(--text)!important;
  transition:border-color .15s ease,background .15s ease;}
.amb-search input::placeholder{color:var(--muted);}
.amb-search input:focus{border-color:var(--gold);background:var(--raised);}
.amb-search kbd{position:absolute;right:9px;top:8px;font:500 .7rem var(--body);color:var(--muted);border:1px solid var(--line2);
  border-radius:3px;padding:1px 6px;}
.amb-search input:focus ~ kbd{display:none;}
.amb-search ul{display:none;position:absolute;top:42px;left:0;right:0;margin:0;padding:4px;list-style:none;background:var(--raised);
  border:1px solid var(--line2);border-radius:var(--r);box-shadow:0 14px 34px rgba(0,0,0,.45);max-height:360px;overflow:auto;}
.amb-search.open ul{display:block;}
.amb-search li{display:flex;gap:10px;align-items:baseline;padding:8px 10px;border-radius:var(--r-sm);cursor:pointer;}
.amb-search li b{font:600 .86rem var(--body);color:var(--text);min-width:52px;}
.amb-search li span{color:var(--text2);font-size:.84rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.amb-search li.on,.amb-search li[data-s]:hover{background:rgba(127,167,255,.12);}
.amb-search li.hint{color:var(--muted);font-size:.82rem;cursor:default;}
@media (max-width:1180px){.st-key-amb_search{width:230px!important;right:190px;}}
@media (max-width:900px){.st-key-amb_search{position:relative!important;top:auto;right:auto;width:100%!important;margin-bottom:6px;z-index:auto;}}
.amb-search ul{z-index:50;}

/* no text cursor on text that can't be edited (Chrome's caret browsing showed one everywhere) */
body *:not(input):not(textarea):not([contenteditable="true"]){caret-color:transparent;}

/* 11. PHONE ------------------------------------------------------------------ */
@media (max-width:640px){
  .block-container{padding-left:16px!important;padding-right:16px!important;padding-top:3.8rem!important;}
  .amb-hero{margin-bottom:14px;}
  .amb-clocks,.amb-sec .right{display:none;}
  .amb-grid,.amb-grid.g3,.amb-grid.g2{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;}
  .amb-grid.g3.stack,.amb-grid.g2.stack{grid-template-columns:1fr;}
  .amb-tile{padding:12px 11px 10px;}
  .amb-tile .val{font-size:1.15rem;}
  .amb-tile .name{font-size:.76rem;}
  .amb-tile .foot{font-size:.6rem;}
  .amb-row{grid-template-columns:22px 1fr auto;}
  .amb-row .p{display:none;}
  .amb-verdict .big{font-size:1.45rem;}
  .amb-stock .stats{gap:4px;}
}

/* 12. MOTION FLOOR ---------------------------------------------------------- */
@media (prefers-reduced-motion:reduce){
  .amb-tape-track{animation:none;}
  .amb-tile,.amb-stock,.amb-tk,div[data-testid="stButton"] button{transition:none;transform:none!important;}
  .amb-dot.on{animation:none;}
}
</style>
"""


def inject_css():
    st.html(CSS)


def show(markup: str):
    st.html(markup)


esc = html.escape

# --------------------------------------------------------------------------- clickable HTML
# A tiny inline component: renders trusted HTML into the page and reports which element
# with a data-go attribute was clicked, without starting a new session.
_CLICK_JS = """
export default function(component) {
  const { data, setTriggerValue, parentElement } = component;
  let root = parentElement.querySelector(':scope > .amb-click');
  if (!root) { root = document.createElement('div'); root.className = 'amb-click'; parentElement.appendChild(root); }
  if (root.__html !== data) { root.innerHTML = data || ''; root.__html = data; }
  root.onclick = (e) => {
    const el = e.target.closest('[data-go]');
    if (el && root.contains(el)) { e.preventDefault(); setTriggerValue('go', el.getAttribute('data-go')); }
  };
  root.onkeydown = (e) => {
    const el = e.target.closest('[data-go]');
    if (el && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); setTriggerValue('go', el.getAttribute('data-go')); }
  };
}
"""
_click = st.components.v2.component("amb_click", js=_CLICK_JS, isolate_styles=False)


def clickable(markup: str, key: str) -> str | None:
    """Render HTML; return the data-go value of the element clicked in this run, if any."""
    r = _click(data=markup, key=key, on_go_change=lambda: None)
    return getattr(r, "go", None)


def go_attr(target: str | None) -> str:
    return f' data-go="{esc(target)}" role="button" tabindex="0"' if target else ""


# --------------------------------------------------------------------------- formatting
def is_num(x) -> bool:
    return isinstance(x, (int, float)) and not (isinstance(x, float) and math.isnan(x))


def money(x, dec: int = 2, cur: str = "$") -> str:
    if not is_num(x):
        return "—"
    if abs(x) >= 10000:
        dec = 0
    return f"{'-' if x < 0 else ''}{cur}{abs(x):,.{dec}f}"


def pct(x, dec: int = 1, signed: bool = True, frac: bool = True) -> str:
    """frac=True: 0.05 -> +5.0%. frac=False: 5 -> +5.0%."""
    if not is_num(x):
        return "—"
    v = x * 100 if frac else x
    return f"{v:+.{dec}f}%" if signed else f"{v:.{dec}f}%"


def big(x, cur: str = "$") -> str:
    if not is_num(x):
        return "—"
    a = abs(x)
    for d, s in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if a >= d:
            return f"{'-' if x < 0 else ''}{cur}{a / d:,.1f}{s}"
    return f"{'-' if x < 0 else ''}{cur}{a:,.0f}"


def mult(x) -> str:
    return f"{x:,.1f}x" if is_num(x) and x > 0 else "—"


def tone(x) -> str:
    if not is_num(x) or abs(x) < 1e-9:
        return "flat"
    return "up" if x > 0 else "down"


def pill(x, frac: bool = False, dec: int = 2, suffix: str = "") -> str:
    """Change pill. By default x is already in percent (Finnhub style)."""
    if not is_num(x):
        return ""
    return f'<span class="amb-pill {tone(x)}">{pct(x, dec, True, frac)}{suffix}</span>'


def chip(text: str, kind: str = "plain") -> str:
    return f'<span class="amb-chip {kind}">{esc(text)}</span>'


def clock(t: dt.datetime | None) -> str:
    """'14:32' for today, 'Oct 27' otherwise."""
    if not t:
        return ""
    return t.strftime("%H:%M") if t.date() == dt.datetime.now(t.tzinfo).date() else t.strftime("%b %d")


def status(t: dt.datetime | None, market_open: bool) -> str:
    """Plain-words freshness: 'Live 10:31', '15 min delay', 'Close Oct 27'."""
    if t is None:
        return '<span class="amb-status"><i></i>n/a</span>'
    if not market_open:
        when = "4:00 PM ET" if t.date() == dt.datetime.now(t.tzinfo).date() else t.strftime("%b %d")
        return f'<span class="amb-status" title="Market closed: this is the last trade">Close · {when}</span>'
    age = (dt.datetime.now(t.tzinfo) - t).total_seconds() / 60
    if age <= 5:
        return f'<span class="amb-status live" title="Traded in the last 5 minutes"><i></i>Live {t:%H:%M}</span>'
    return f'<span class="amb-status delayed" title="Last trade was {int(age)} minutes ago"><i></i>{int(age)} min delay</span>'


# --------------------------------------------------------------------------- components
def spark(series: pd.Series | list, w: int = 220, h: int = 40, color: str | None = None) -> str:
    """Sparkline as an SVG image (data URI)."""
    vals = [float(v) for v in (series.dropna().tolist() if isinstance(series, pd.Series) else series) if is_num(v)]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    n = len(vals)
    pts = [(i * w / (n - 1), h - 3 - (v - lo) / rng * (h - 6)) for i, v in enumerate(vals)]
    col = color or (C["up"] if vals[-1] >= vals[0] else C["down"])
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
           f'<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
           f'<stop offset="0" stop-color="{col}" stop-opacity=".25"/><stop offset="1" stop-color="{col}" stop-opacity="0"/>'
           f'</linearGradient></defs>'
           f'<polygon points="0,{h} {line} {w},{h}" fill="url(#g)"/>'
           f'<polyline points="{line}" fill="none" stroke="{col}" stroke-width="1.5" stroke-linejoin="round" '
           f'vector-effect="non-scaling-stroke"/></svg>')
    uri = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
    return f'<img src="{uri}" alt="" style="display:block;width:100%;height:{h}px">'


def range_bar(lo, hi, cur, title: str = "", fmt=money) -> str:
    """Where today's price sits between two bounds (e.g. day low/high, 52-week low/high)."""
    if not (is_num(lo) and is_num(hi) and is_num(cur)) or hi <= lo:
        return ""
    p = min(max((cur - lo) / (hi - lo), 0), 1) * 100
    lab = f'<div class="lab"><span>{esc(title)}</span></div>' if title else ""
    return (f'<div class="amb-range">{lab}<div class="bar"><div class="fill"></div>'
            f'<div class="mark" style="left:calc({p:.1f}% - 1px)"></div></div>'
            f'<div class="ends"><span>{fmt(lo)}</span><span>{fmt(hi)}</span></div></div>')


def tile(name: str, value: str, change: str = "", tick: str = "", foot_l: str = "", extra: str = "",
         go: str | None = None, hint: str = "Analyze →") -> str:
    hint_html = f'<span class="go-hint">{esc(hint)}</span>' if go else ""
    return (f'<div class="amb-tile"{go_attr(go)}>'
            f'<div class="eyebrow"><span class="name">{esc(name)}</span><span class="tick">{esc(tick)}</span></div>'
            f'<div class="val">{value}</div><div class="chg">{change}</div>{extra}'
            f'<div class="foot"><span>{foot_l}</span>{hint_html}</div></div>')


def grid(items: list[str], cls: str = "") -> str:
    return f'<div class="amb-grid {cls}">{"".join(items)}</div>'


def section(title: str, right: str = "", eyebrow: str = "") -> None:
    """Section heading with a short description on the right. `eyebrow` is accepted for older
    calls but no longer drawn: a label above every heading only repeats it."""
    show(f'<div class="amb-sec"><div><h2>{esc(title)}</h2></div><div class="right">{right}</div></div>')


def tape(items: list[tuple]) -> str:
    """Scrolling ticker tape. Items are (label, value, % change) or (label, value, % change, click target)."""
    def cell(it):
        a, b, c = it[:3]
        go = it[3] if len(it) > 3 else None
        return (f'<div class="amb-tape-item"{go_attr(go)}><span class="t-s">{esc(a)}</span>'
                f'<span class="t-p">{b}</span>{pill(c)}</div>')
    cells = "".join(cell(it) for it in items)
    return f'<div class="amb-tape"><div class="amb-tape-track">{cells}{cells}</div></div>'


def logo(url: str, sym: str, size: int = 34) -> str:
    st_ = f'style="width:{size}px;height:{size}px;border-radius:{max(size // 4, 6)}px;font-size:{size * 0.45:.0f}px"'
    if url:
        return f'<img class="amb-logo" src="{esc(url)}" alt="" {st_}>'
    return f'<div class="amb-logo ph" {st_}>{esc(sym[:1])}</div>'


def news_list(items: list[dict], limit: int = 12) -> str:
    if not items:
        return '<div class="amb-empty">No recent headlines.</div>'
    rows = []
    for it in items[:limit]:
        when = it["time"].strftime("%b %d · %H:%M ET") if it.get("time") else ""
        mk = chip(it.get("market", "US"), it.get("market", "US"))
        rows.append(f'<a class="n" href="{esc(it["url"])}" target="_blank" rel="noopener">{mk}'
                    f'<span class="t">{esc(it["title"])}</span><span class="m">{esc(it["source"])} · {when}</span></a>')
    return f'<div class="amb-news">{"".join(rows)}</div>'


def kv(items: list[tuple[str, str, str]]) -> str:
    cells = "".join(f'<div class="c"><div class="k">{esc(k)}</div><div class="v">{v}</div>'
                    f'{f"<div class=h>{esc(h)}</div>" if h else ""}</div>' for k, v, h in items)
    return f'<div class="amb-kv">{cells}</div>'


def footer(text: str) -> None:
    show(f'<div class="amb-foot"><span>Alejandro Market Brief</span><span>{text}</span></div>')


# --------------------------------------------------------------------------- plotly
pio.templates["amb"] = go.layout.Template(layout=go.Layout(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter Tight, system-ui, sans-serif", color=C["text2"], size=12),
    colorway=SERIES,
    xaxis=dict(gridcolor="rgba(0,0,0,0)", linecolor=C["line2"], zeroline=False, tickfont=dict(color=C["muted"])),
    yaxis=dict(gridcolor=C["line"], zeroline=False, tickfont=dict(family="Inter Tight", color=C["muted"]), side="left",
               automargin=True),
    hoverlabel=dict(bgcolor=C["raised"], bordercolor=C["line2"], font=dict(family="Inter Tight", color=C["text"])),
    legend=dict(orientation="h", y=1.1, x=0, font=dict(color=C["text2"])),
    margin=dict(l=8, r=16, t=40, b=8), hovermode="x unified",
))
pio.templates.default = "amb"


def plot(fig: go.Figure, height: int = 340, title: str | None = None):
    if title:
        fig.update_layout(title=dict(text=title, font=dict(family="Spectral, Georgia, serif", size=16, color=C["text"]), x=0.01))
    fig.update_layout(height=height)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
