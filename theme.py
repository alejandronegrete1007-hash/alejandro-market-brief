"""Look and feel: CSS, small HTML components, number formatting and the Plotly theme."""
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
    "bg": "#07090D", "card": "#0D1117", "raised": "#131922", "line": "#1E2632", "line2": "#2A3442",
    "text": "#E9EEF4", "text2": "#A7B1BF", "muted": "#6E7A8A",
    "gold": "#E8B04B", "up": "#2BD67B", "down": "#FF5C6C", "us": "#6EA8FE", "mx": "#2EC5A1",
}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
:root{
  --bg:#07090D;--card:#0D1117;--raised:#131922;--line:#1E2632;--line2:#2A3442;
  --text:#E9EEF4;--text2:#A7B1BF;--muted:#6E7A8A;--gold:#E8B04B;--up:#2BD67B;--down:#FF5C6C;--us:#6EA8FE;--mx:#2EC5A1;
  --display:'Space Grotesk',system-ui,sans-serif;--body:'Inter',system-ui,sans-serif;--mono:'JetBrains Mono',ui-monospace,monospace;
}
html,body,[data-testid="stAppViewContainer"]{background:var(--bg)!important;}
[data-testid="stAppViewContainer"]{
  background:radial-gradient(1200px 500px at 85% -120px,rgba(232,176,75,.07),transparent 60%),
             radial-gradient(900px 400px at -10% 0,rgba(46,197,161,.05),transparent 60%),var(--bg)!important;}
[data-testid="stHeader"]{background:rgba(7,9,13,.82)!important;backdrop-filter:blur(14px);border-bottom:1px solid var(--line);}
[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"]{display:none!important;}
.block-container{padding-top:4.6rem!important;padding-bottom:4rem!important;max-width:1320px!important;}
html,body,p,li,span,div,label,input,button,textarea{font-family:var(--body);}
h1,h2,h3,h4{font-family:var(--display)!important;letter-spacing:-.02em;color:var(--text);}
p,li{color:var(--text2);}
a{color:var(--gold)!important;text-decoration:none;}
::selection{background:rgba(232,176,75,.3);}

/* top navigation */
[data-testid="stHeader"] a[href]{font-family:var(--display)!important;font-weight:500;letter-spacing:.01em;}

/* streamlit widgets */
[data-testid="stTabs"] button[role="tab"]{font-family:var(--display);font-weight:500;color:var(--muted);}
[data-testid="stTabs"] button[aria-selected="true"]{color:var(--text);}
[data-testid="stTabs"] [data-baseweb="tab-highlight"]{background:var(--gold)!important;}
[data-testid="stExpander"] details{border:1px solid var(--line)!important;border-radius:14px!important;background:var(--card);}
div[data-testid="stButton"] button,div[data-testid="stFormSubmitButton"] button{
  border-radius:10px;border:1px solid var(--line2);background:var(--raised);font-weight:500;transition:all .15s;}
div[data-testid="stButton"] button:hover{border-color:var(--gold);color:var(--gold);}
div[data-testid="stButton"] button[kind="primary"]{background:var(--gold);border-color:var(--gold);}
div[data-testid="stButton"] button[kind="primary"] *,div[data-testid="stButton"] button[kind="primary"]{color:#14100A!important;font-weight:600;}
div[data-testid="stButton"] button[kind="primary"]:hover{filter:brightness(1.08);}
[data-testid="stMetric"]{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;}
[data-testid="stPlotlyChart"]{border:1px solid var(--line);border-radius:16px;background:var(--card);overflow:hidden;}
[data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:14px;overflow:hidden;}

/* --------- custom components --------- */
.amb-hero{display:flex;justify-content:space-between;align-items:flex-end;gap:24px;flex-wrap:wrap;margin:6px 0 18px;}
.amb-kicker{font-family:var(--mono);font-size:.72rem;letter-spacing:.18em;text-transform:uppercase;color:var(--gold);margin-bottom:8px;}
.amb-hero h1{font-size:clamp(2.1rem,4.6vw,3.5rem);line-height:1.02;margin:0;font-weight:600;}
.amb-hero .sub{color:var(--text2);margin-top:10px;font-size:.95rem;display:flex;gap:14px;flex-wrap:wrap;align-items:center;}
.amb-clocks{display:flex;gap:10px;}
.amb-clock{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:8px 12px;min-width:118px;}
.amb-clock .c-l{font-family:var(--mono);font-size:.66rem;letter-spacing:.14em;color:var(--muted);text-transform:uppercase;}
.amb-clock .c-v{font-family:var(--mono);font-size:1.05rem;color:var(--text);margin-top:2px;}
.amb-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;vertical-align:middle;}
.amb-dot.on{background:var(--up);box-shadow:0 0 0 4px rgba(43,214,123,.15);animation:amb-pulse 2s infinite;}
.amb-dot.off{background:var(--muted);}
@keyframes amb-pulse{50%{box-shadow:0 0 0 7px rgba(43,214,123,0);}}

.amb-tape{position:relative;overflow:hidden;border-top:1px solid var(--line);border-bottom:1px solid var(--line);
  background:linear-gradient(90deg,var(--bg),transparent 6%,transparent 94%,var(--bg)),var(--card);margin:0 0 28px;
  mask-image:linear-gradient(90deg,transparent,#000 6%,#000 94%,transparent);}
.amb-tape-track{display:flex;width:max-content;animation:amb-scroll 60s linear infinite;}
.amb-tape:hover .amb-tape-track{animation-play-state:paused;}
.amb-tape-item{display:flex;gap:10px;align-items:baseline;padding:11px 22px;border-right:1px solid var(--line);white-space:nowrap;}
.amb-tape-item .t-s{font-family:var(--display);font-weight:600;color:var(--text);font-size:.85rem;}
.amb-tape-item .t-p{font-family:var(--mono);color:var(--text2);font-size:.85rem;}
@keyframes amb-scroll{to{transform:translateX(-50%);}}
@media (prefers-reduced-motion:reduce){.amb-tape-track{animation:none;}}

.amb-sec{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin:30px 0 14px;}
.amb-sec h2{font-size:1.35rem;margin:0;font-weight:600;display:flex;align-items:center;gap:10px;}
.amb-sec .right{color:var(--muted);font-size:.8rem;font-family:var(--mono);}

.amb-grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(182px,1fr));}
.amb-grid.g3{grid-template-columns:repeat(auto-fill,minmax(300px,1fr));}
.amb-tile{position:relative;background:linear-gradient(180deg,var(--raised),var(--card));border:1px solid var(--line);
  border-radius:16px;padding:16px 16px 14px;overflow:hidden;transition:border-color .2s,transform .2s;}
.amb-tile:hover{border-color:var(--line2);transform:translateY(-1px);}
.amb-tile .lbl{display:flex;justify-content:space-between;align-items:center;gap:8px;color:var(--text2);font-size:.8rem;font-weight:500;}
.amb-tile .val{font-family:var(--mono);font-size:1.55rem;font-weight:500;color:var(--text);margin:8px 0 6px;letter-spacing:-.02em;}
.amb-tile .foot{display:flex;justify-content:space-between;align-items:center;gap:8px;color:var(--muted);font-size:.72rem;font-family:var(--mono);margin-top:8px;}
.amb-tile .spark{margin:4px -4px -2px;}
.amb-tile.accent-mx{box-shadow:inset 3px 0 0 var(--mx);}
.amb-tile.accent-us{box-shadow:inset 3px 0 0 var(--us);}

.amb-pill{font-family:var(--mono);font-size:.76rem;font-weight:500;padding:3px 8px;border-radius:999px;white-space:nowrap;}
.amb-pill.up{color:var(--up);background:rgba(43,214,123,.1);}
.amb-pill.down{color:var(--down);background:rgba(255,92,108,.1);}
.amb-pill.flat{color:var(--text2);background:rgba(167,177,191,.1);}
.amb-chip{font-family:var(--mono);font-size:.62rem;font-weight:600;letter-spacing:.12em;padding:3px 7px;border-radius:6px;text-transform:uppercase;white-space:nowrap;}
.amb-chip.US{color:var(--us);background:rgba(110,168,254,.1);border:1px solid rgba(110,168,254,.25);}
.amb-chip.MX{color:var(--mx);background:rgba(46,197,161,.1);border:1px solid rgba(46,197,161,.25);}
.amb-chip.GLOBAL{color:var(--gold);background:rgba(232,176,75,.1);border:1px solid rgba(232,176,75,.25);}
.amb-chip.live{color:var(--up);border:1px solid rgba(43,214,123,.3);}
.amb-chip.delayed{color:var(--gold);border:1px solid rgba(232,176,75,.3);}
.amb-chip.close,.amb-chip.daily{color:var(--muted);border:1px solid var(--line2);}

.amb-range{margin-top:10px;}
.amb-range .bar{position:relative;height:4px;border-radius:4px;background:var(--line2);}
.amb-range .fill{position:absolute;top:0;bottom:0;border-radius:4px;background:linear-gradient(90deg,var(--down),var(--gold),var(--up));opacity:.55;}
.amb-range .mark{position:absolute;top:-4px;width:2px;height:12px;background:var(--text);border-radius:2px;}
.amb-range .ends{display:flex;justify-content:space-between;font-family:var(--mono);font-size:.66rem;color:var(--muted);margin-top:5px;}

.amb-brief{display:grid;grid-template-columns:1fr 1fr;gap:12px;}
@media (max-width:820px){.amb-brief{grid-template-columns:1fr;}}
.amb-take{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 20px;}
.amb-take .h{display:flex;gap:10px;align-items:center;margin-bottom:8px;font-family:var(--display);font-weight:600;color:var(--text);}
.amb-take p{margin:0;line-height:1.65;color:var(--text2);font-size:.96rem;}
.amb-lead{font-family:var(--display);font-size:clamp(1.35rem,2.6vw,1.9rem);line-height:1.2;color:var(--text);margin:4px 0 16px;font-weight:600;}
.amb-lead span{color:var(--gold);}

.amb-story{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 20px;display:flex;flex-direction:column;gap:10px;}
.amb-story .top{display:flex;gap:8px;align-items:center;}
.amb-story .rank{font-family:var(--mono);color:var(--muted);font-size:.75rem;}
.amb-story h3{font-size:1.08rem;margin:0;line-height:1.3;font-weight:600;}
.amb-story .row{font-size:.9rem;line-height:1.55;color:var(--text2);}
.amb-story .row b{color:var(--text);font-weight:600;font-size:.72rem;letter-spacing:.1em;text-transform:uppercase;font-family:var(--mono);display:block;margin-bottom:2px;}
.amb-srcs{display:flex;flex-wrap:wrap;gap:6px;margin-top:auto;padding-top:6px;}
.amb-src{font-family:var(--mono);font-size:.68rem;color:var(--text2)!important;border:1px solid var(--line2);border-radius:999px;padding:3px 9px;}
.amb-src:hover{border-color:var(--gold);color:var(--gold)!important;}

.amb-news{display:flex;flex-direction:column;}
.amb-news a.n{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;padding:12px 4px;border-bottom:1px solid var(--line);color:var(--text)!important;}
.amb-news a.n:hover .t{color:var(--gold);}
.amb-news .t{font-weight:500;line-height:1.35;color:var(--text);}
.amb-news .m{grid-column:2;font-family:var(--mono);font-size:.68rem;color:var(--muted);}

.amb-rail{display:flex;flex-direction:column;gap:8px;}
.amb-mini{display:grid;grid-template-columns:1fr auto;gap:2px 10px;align-items:center;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 12px;}
.amb-mini .s{font-family:var(--display);font-weight:600;color:var(--text);}
.amb-mini .n{font-size:.72rem;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:150px;}
.amb-mini .p{font-family:var(--mono);color:var(--text);text-align:right;font-size:.9rem;}

.amb-stock{background:linear-gradient(180deg,var(--raised),var(--card));border:1px solid var(--line);border-radius:18px;padding:18px;}
.amb-stock .hd{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;}
.amb-stock .sym{font-family:var(--display);font-size:1.4rem;font-weight:700;color:var(--text);line-height:1;}
.amb-stock .nm{color:var(--muted);font-size:.8rem;margin-top:4px;}
.amb-stock .px{font-family:var(--mono);font-size:1.3rem;color:var(--text);text-align:right;}
.amb-stock .stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:12px;}
.amb-stock .st{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:8px 10px;}
.amb-stock .st .k{font-size:.62rem;font-family:var(--mono);letter-spacing:.12em;color:var(--muted);text-transform:uppercase;}
.amb-stock .st .v{font-family:var(--mono);color:var(--text);font-size:.92rem;margin-top:2px;}
.amb-logo{width:34px;height:34px;border-radius:9px;background:#fff;object-fit:contain;padding:3px;}
.amb-logo.ph{display:flex;align-items:center;justify-content:center;background:var(--line2);color:var(--text);font-family:var(--display);font-weight:700;}

.amb-lb{width:100%;border-collapse:collapse;}
.amb-lb td,.amb-lb th{padding:12px 10px;border-bottom:1px solid var(--line);text-align:left;}
.amb-lb th{font-family:var(--mono);font-size:.66rem;letter-spacing:.14em;color:var(--muted);text-transform:uppercase;font-weight:500;}
.amb-lb td{color:var(--text2);font-size:.9rem;}
.amb-lb td.num{font-family:var(--mono);text-align:right;color:var(--text);}
.amb-lb th.num{text-align:right;}
.amb-lb .rk{font-family:var(--mono);color:var(--muted);width:34px;}
.amb-lb tr.top .rk{color:var(--gold);}
.amb-lb .bar{height:6px;border-radius:6px;background:var(--up);opacity:.75;}
.amb-lb .bar.neg{background:var(--down);}
.amb-wrap{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:6px 14px;overflow-x:auto;}

.amb-kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;}
.amb-kv .c{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 14px;}
.amb-kv .k{font-size:.72rem;color:var(--muted);}
.amb-kv .v{font-family:var(--mono);font-size:1.15rem;color:var(--text);margin-top:4px;}
.amb-kv .h{font-size:.7rem;color:var(--muted);margin-top:4px;line-height:1.35;}

.amb-verdict{border-radius:18px;padding:20px 22px;border:1px solid var(--line);background:var(--card);display:flex;gap:24px;flex-wrap:wrap;align-items:center;justify-content:space-between;}
.amb-verdict .big{font-family:var(--display);font-size:1.9rem;font-weight:700;}
.amb-verdict.under{border-color:rgba(43,214,123,.35);background:linear-gradient(120deg,rgba(43,214,123,.08),var(--card) 55%);}
.amb-verdict.over{border-color:rgba(255,92,108,.35);background:linear-gradient(120deg,rgba(255,92,108,.08),var(--card) 55%);}
.amb-verdict.fair{border-color:rgba(232,176,75,.35);background:linear-gradient(120deg,rgba(232,176,75,.08),var(--card) 55%);}
.amb-verdict .nums{display:flex;gap:28px;flex-wrap:wrap;}
.amb-verdict .nums .k{font-family:var(--mono);font-size:.66rem;letter-spacing:.14em;color:var(--muted);text-transform:uppercase;}
.amb-verdict .nums .v{font-family:var(--mono);font-size:1.35rem;color:var(--text);}

.amb-tag{font-family:var(--mono);font-size:.62rem;letter-spacing:.12em;text-transform:uppercase;padding:2px 7px;border-radius:5px;margin-right:6px;}
.amb-tag.data{color:var(--us);background:rgba(110,168,254,.1);}
.amb-tag.calc{color:var(--gold);background:rgba(232,176,75,.1);}
.amb-tag.ai{color:#C792EA;background:rgba(199,146,234,.1);}
.amb-note{color:var(--muted);font-size:.78rem;line-height:1.5;margin-top:10px;}
.amb-empty{border:1px dashed var(--line2);border-radius:16px;padding:22px;color:var(--muted);text-align:center;}
.amb-foot{margin-top:48px;padding-top:18px;border-top:1px solid var(--line);display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;color:var(--muted);font-size:.75rem;font-family:var(--mono);}

@media (max-width:640px){
  .block-container{padding-left:16px!important;padding-right:16px!important;}
  .amb-sec .right{display:none;}
  .amb-clocks{display:none;}
  .amb-grid{grid-template-columns:1fr 1fr;}
  .amb-tile .val{font-size:1.2rem;}
  .amb-stock .stats{grid-template-columns:repeat(3,1fr);}
}
</style>
"""


def inject_css():
    st.html(CSS)


def show(markup: str):
    st.html(markup)


esc = html.escape


# --------------------------------------------------------------------------- formatting
def is_num(x) -> bool:
    return isinstance(x, (int, float)) and not (isinstance(x, float) and math.isnan(x))


def money(x, dec: int = 2, cur: str = "$") -> str:
    if not is_num(x):
        return "—"
    if abs(x) >= 10000:
        dec = 0
    return f"{cur}{x:,.{dec}f}"


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
    return f"{cur}{x:,.0f}"


def mult(x) -> str:
    return f"{x:,.1f}x" if is_num(x) and x > 0 else "—"


def tone(x) -> str:
    if not is_num(x) or abs(x) < 1e-9:
        return "flat"
    return "up" if x > 0 else "down"


def pill(x, frac: bool = False, dec: int = 2, suffix: str = "") -> str:
    """Change pill. By default x is already in percent (Finnhub style)."""
    return f'<span class="amb-pill {tone(x)}">{pct(x, dec, True, frac)}{suffix}</span>'


def chip(text: str, kind: str) -> str:
    return f'<span class="amb-chip {kind}">{esc(text)}</span>'


def clock(t: dt.datetime | None) -> str:
    """'14:32' for today, 'Oct 27' otherwise."""
    if not t:
        return ""
    return t.strftime("%H:%M") if t.date() == dt.datetime.now(t.tzinfo).date() else t.strftime("%b %d")


def freshness(t: dt.datetime | None, market_open: bool, daily: bool = False) -> str:
    """Badge that says how current a number is: live, delayed, last close or daily."""
    if daily or t is None:
        return chip("daily", "daily")
    if not market_open:
        return chip("close", "close")
    age = (dt.datetime.now(t.tzinfo) - t).total_seconds() / 60
    return chip("live", "live") if age <= 5 else chip(f"{int(age)}m delay", "delayed")


# --------------------------------------------------------------------------- components
def spark(series: pd.Series | list, w: int = 220, h: int = 44, color: str | None = None) -> str:
    """Sparkline as an SVG image (data URI), which survives Streamlit's HTML sanitizer."""
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
           f'<stop offset="0" stop-color="{col}" stop-opacity=".28"/><stop offset="1" stop-color="{col}" stop-opacity="0"/>'
           f'</linearGradient></defs>'
           f'<polygon points="0,{h} {line} {w},{h}" fill="url(#g)"/>'
           f'<polyline points="{line}" fill="none" stroke="{col}" stroke-width="1.6" stroke-linejoin="round" '
           f'vector-effect="non-scaling-stroke"/></svg>')
    uri = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
    return f'<img src="{uri}" alt="" style="display:block;width:100%;height:{h}px">'


def range_bar(lo, hi, cur, left: str = "", right: str = "", fmt=money) -> str:
    if not (is_num(lo) and is_num(hi) and is_num(cur)) or hi <= lo:
        return ""
    p = min(max((cur - lo) / (hi - lo), 0), 1) * 100
    return (f'<div class="amb-range"><div class="bar"><div class="fill" style="left:0;right:0"></div>'
            f'<div class="mark" style="left:calc({p:.1f}% - 1px)"></div></div>'
            f'<div class="ends"><span>{left} {fmt(lo)}</span><span>{fmt(hi)} {right}</span></div></div>')


def tile(label: str, value: str, change: str = "", foot_l: str = "", foot_r: str = "",
         extra: str = "", accent: str = "") -> str:
    return (f'<div class="amb-tile {("accent-" + accent) if accent else ""}">'
            f'<div class="lbl"><span>{esc(label)}</span>{change}</div>'
            f'<div class="val">{value}</div>{extra}'
            f'<div class="foot"><span>{foot_l}</span><span>{foot_r}</span></div></div>')


def grid(tiles: list[str], cls: str = "") -> str:
    return f'<div class="amb-grid {cls}">{"".join(tiles)}</div>'


def section(title: str, right: str = "", chip_html: str = "") -> None:
    show(f'<div class="amb-sec"><h2>{chip_html}{esc(title)}</h2><div class="right">{right}</div></div>')


def tape(items: list[tuple[str, str, float | None]]) -> str:
    """items: (label, price text, % change already in percent)."""
    cells = "".join(
        f'<div class="amb-tape-item"><span class="t-s">{esc(a)}</span><span class="t-p">{b}</span>{pill(c) if is_num(c) else ""}</div>'
        for a, b, c in items)
    return f'<div class="amb-tape"><div class="amb-tape-track">{cells}{cells}</div></div>'


def logo(url: str, sym: str, size: int = 34) -> str:
    st_ = f'style="width:{size}px;height:{size}px;border-radius:{size // 4}px;font-size:{size * 0.45:.0f}px"'
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
    font=dict(family="Inter, system-ui, sans-serif", color=C["text2"], size=12),
    colorway=[C["gold"], C["mx"], C["us"], "#C792EA", C["up"], C["down"]],
    xaxis=dict(gridcolor="rgba(0,0,0,0)", linecolor=C["line2"], zeroline=False, tickfont=dict(color=C["muted"])),
    yaxis=dict(gridcolor=C["line"], zeroline=False, tickfont=dict(family="JetBrains Mono", color=C["muted"]), side="left",
               automargin=True),
    hoverlabel=dict(bgcolor=C["raised"], bordercolor=C["line2"], font=dict(family="JetBrains Mono", color=C["text"])),
    legend=dict(orientation="h", y=1.08, x=0, font=dict(color=C["text2"])),
    margin=dict(l=8, r=16, t=40, b=8), hovermode="x unified",
))
pio.templates.default = "amb"


def plot(fig: go.Figure, height: int = 360):
    fig.update_layout(height=height)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
