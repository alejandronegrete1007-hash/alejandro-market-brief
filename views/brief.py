"""Today: both markets at a glance and the AI-written daily brief."""
from __future__ import annotations

import datetime as dt

import streamlit as st

import ai
import mexico
import sources as src
import state
import theme as T
from views.common import click, mini_rows

US_SET = [("S&P 500", "SPY"), ("Nasdaq 100", "QQQ"), ("Dow Jones", "DIA"), ("Russell 2000", "IWM"),
          ("Gold", "GLD"), ("Oil · WTI", "USO")]


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception:
        return None


def _etf_tile(label, sym, q, is_open):
    if not q:
        return T.tile(label, "—", tick=sym, foot_l="unavailable")
    return T.tile(label, T.money(q["price"]), T.pill(q["pct"]), tick=f"via {sym}",
                  foot_l=T.status(q["time"], is_open),
                  extra=T.range_bar(q["low"], q["high"], q["price"], "Today's low → high"), go=f"t:{sym}")


def _hero(status):
    now_et, now_mx = dt.datetime.now(src.ET), dt.datetime.now(src.MX)
    us = ('<span><span class="amb-dot on"></span>NYSE open</span>' if status["open"]
          else '<span><span class="amb-dot off"></span>NYSE closed · prices are the last close</span>')
    bmv = ('<span><span class="amb-dot on"></span>BMV open</span>' if src.bmv_open()
           else '<span><span class="amb-dot off"></span>BMV closed</span>')
    T.show(f"""
    <div class="amb-hero">
      <div><div class="amb-eyebrow">Daily brief · Wall Street &amp; México</div>
        <h1>{now_mx:%A, %B} {now_mx.day}</h1>
        <div class="sub">{us}{bmv}</div></div>
      <div class="amb-clocks">
        <div class="amb-clock"><div class="c-l">New York</div><div class="c-v">{now_et:%H:%M}</div></div>
        <div class="amb-clock"><div class="c-l">CDMX</div><div class="c-v">{now_mx:%H:%M}</div></div>
      </div>
    </div>""")


def render():
    status = src.us_market_status()
    is_open = status["open"]
    _hero(status)

    quotes = {sym: src.try_quote(sym) for _, sym in US_SET}
    eww = src.try_quote("EWW")
    btc = _safe(src.bitcoin)
    t10 = _safe(src.fred, "DGS10")
    fed = _safe(src.fred, "DFEDTARU")
    bx = _safe(mexico.indicators) or {}
    fix = _safe(mexico.fix_history, 400)
    S = mexico.SERIES

    items = [(lbl, T.money(q["price"]), q["pct"]) for (lbl, s), q in ((x, quotes[x[1]]) for x in US_SET) if q]
    if btc:
        items.append(("Bitcoin", T.money(btc["price"], 0), btc["pct"]))
    if fix is not None and len(fix) > 1:
        items.append(("USD/MXN", f"{fix.iloc[-1]:.4f}", (fix.iloc[-1] / fix.iloc[-2] - 1) * 100))
    if eww:
        items.append(("México · EWW", T.money(eww["price"]), eww["pct"]))
    if items:
        T.show(T.tape(items))

    main, rail = st.columns([2.9, 1], gap="large")
    with main:
        # ---------------- Wall Street
        T.section("Wall Street", "index ETFs · click any card to analyze it", "United States")
        tiles = [_etf_tile(l, s, quotes[s], is_open) for l, s in US_SET]
        if btc:
            tiles.append(T.tile("Bitcoin", T.money(btc["price"], 0), T.pill(btc["pct"], suffix=" 24h"), tick="BTC",
                                foot_l=f"24/7 market · {T.clock(btc['time'])}"))
        if t10 is not None and len(t10) > 1:
            bps = (t10.iloc[-1] - t10.iloc[-2]) * 100
            tiles.append(T.tile("US 10-year yield", f"{t10.iloc[-1]:.2f}%",
                                f'<span class="amb-pill {T.tone(bps)}">{bps:+.0f} bps</span>', tick="UST",
                                foot_l=f"Daily · {t10.index[-1]:%b %d}",
                                extra=f'<div class="spark">{T.spark(t10.iloc[-120:], color=T.C["gold"])}</div>'))
        click(T.grid(tiles), "tiles_us")
        T.show('<div class="amb-note">The S&amp;P 500, Nasdaq, Dow and Russell are followed through the ETFs that track them '
               '(SPY, QQQ, DIA, IWM), whose daily % move is almost identical. The bar shows where the price sits between '
               "today's low and high. <b>Close</b> means the market is shut and you see the last trade of the day.</div>")

        # ---------------- Mexico
        T.section("México", "Banxico · NYSE-listed Mexican stocks", "Mexico")
        tiles = []
        if fix is not None and len(fix) > 1:
            chg = (fix.iloc[-1] / fix.iloc[-2] - 1) * 100
            base = fix[fix.index < dt.datetime(fix.index[-1].year, 1, 1)]
            ytd = (fix.iloc[-1] / base.iloc[-1] - 1) * 100 if len(base) else None
            tiles.append(T.tile("Dollar in pesos", f"{fix.iloc[-1]:.4f}", T.pill(chg), tick="FIX",
                                foot_l=f"Banxico · {fix.index[-1]:%b %d}" + (f" · YTD {T.pct(ytd, 1, frac=False)}" if ytd is not None else ""),
                                extra=f'<div class="spark">{T.spark(fix.iloc[-90:], color=T.C["mx"])}</div>',
                                go="p:mexico", hint="Charts →"))
        if eww:
            tiles.append(T.tile("Mexican stocks", T.money(eww["price"]), T.pill(eww["pct"]), tick="via EWW",
                                foot_l=T.status(eww["time"], is_open),
                                extra=T.range_bar(eww["low"], eww["high"], eww["price"], "Today's low → high"), go="t:EWW"))
        if S["target"] in bx:
            b = bx[S["target"]]
            carry = (f'<div class="amb-note" style="margin-top:6px">vs Fed: <b style="color:var(--text)">{b["value"] - fed.iloc[-1]:+.2f} pts</b></div>'
                     if fed is not None else "")
            tiles.append(T.tile("Banxico rate", f"{b['value']:.2f}%", tick="TARGET", foot_l=f"Official · {b['date']:%b %d}",
                                extra=carry, go="p:mexico", hint="Charts →"))
        if S["inflation"] in bx:
            b = bx[S["inflation"]]
            inside = abs(b["value"] - mexico.INFLATION_TARGET) <= 1
            tiles.append(T.tile("Inflation", f"{b['value']:.2f}%",
                                f'<span class="amb-pill {"up" if inside else "down"}">{"inside 2–4% target" if inside else "outside target"}</span>',
                                tick="INPC", foot_l=f"Annual · {b['date']:%b %Y}", go="p:mexico", hint="Charts →"))
        if S["cetes28"] in bx:
            b = bx[S["cetes28"]]
            tiles.append(T.tile("CETES 28 days", f"{b['value']:.2f}%", tick="AUCTION", foot_l=f"Weekly · {b['date']:%b %d}",
                                go="p:mexico", hint="Charts →"))
        if S["tiie28"] in bx:
            b = bx[S["tiie28"]]
            tiles.append(T.tile("TIIE 28 days", f"{b['value']:.2f}%", tick="TIIE", foot_l=f"Daily · {b['date']:%b %d}",
                                go="p:mexico", hint="Charts →"))
        if S["target"] in bx and S["inflation"] in bx:
            real = bx[S["target"]]["value"] - bx[S["inflation"]]["value"]
            tiles.append(T.tile("Real policy rate", f"{real:.2f}%", tick="CALC", foot_l="Banxico rate − inflation",
                                extra='<div class="amb-note" style="margin-top:6px">Above ~2% = tight money</div>'))
        lead = _safe(mexico.leaderboard)
        if lead and lead[0]["ytd"] is not None:
            r = lead[0]
            tiles.append(T.tile("Top Mexican stock YTD", T.esc(r["symbol"]), T.pill(r["ytd"] * 100), tick="ADR",
                                foot_l=T.esc(r["name"][:24]), go=f"t:{r['symbol']}"))
        if tiles:
            click(T.grid(tiles), "tiles_mx")
        else:
            T.show('<div class="amb-empty">Mexico data unavailable. Check BANXICO_TOKEN in Secrets.</div>')
        brief_slot = st.container()

    with rail:
        T.section("Watchlist", "", "Click to analyze")
        T.show(f'<div class="amb-th" style="margin:2px 0 8px">S&amp;P 500 leaders 2026 {T.chip("US", "US")}</div>')
        click(mini_rows(state.US_LEADERS), "rail_us")
        mx_syms, live = state.mx_leaders()
        T.show(f'<div class="amb-th" style="margin:16px 0 8px">{"Mexico top 5 YTD" if live else "Mexico picks"} {T.chip("MX", "MX")}</div>')
        click(mini_rows(mx_syms), "rail_mx")
        mine = state.my_list()
        if mine:
            T.show('<div class="amb-th" style="margin:16px 0 8px">My stocks</div>')
            click(mini_rows(mine[:8]), "rail_my")

    with brief_slot:
        _brief(quotes, eww, btc, t10, bx, fix)
    T.footer("Not investment advice · Finnhub, Twelve Data, FRED, Banxico, SEC, CoinGecko")


def _snapshot(quotes, eww, btc, t10, bx, fix) -> str:
    lines = []
    for (lbl, s) in US_SET:
        q = quotes.get(s)
        if q:
            lines.append(f"{lbl} via {s}: {q['price']:.2f} ({q['pct']:+.2f}% on the day)")
    if btc:
        lines.append(f"Bitcoin: {btc['price']:,.0f} ({(btc['pct'] or 0):+.2f}% in 24h)")
    if t10 is not None and len(t10) > 1:
        lines.append(f"US 10-year Treasury yield: {t10.iloc[-1]:.2f}% ({(t10.iloc[-1] - t10.iloc[-2]) * 100:+.0f} bps)")
    if fix is not None and len(fix) > 1:
        lines.append(f"USD/MXN FIX: {fix.iloc[-1]:.4f} ({(fix.iloc[-1] / fix.iloc[-2] - 1) * 100:+.2f}%; higher = weaker peso)")
    if eww:
        lines.append(f"Mexican stocks via EWW ETF: {eww['price']:.2f} ({eww['pct']:+.2f}%)")
    for k, lbl in {"target": "Banxico target rate", "cetes28": "CETES 28-day yield", "tiie28": "TIIE 28",
                   "inflation": "Mexico annual inflation"}.items():
        b = bx.get(mexico.SERIES[k])
        if b:
            lines.append(f"{lbl}: {b['value']:.2f}% (as of {b['date']})")
    return "\n".join(lines)


def _fmt_headline(h: dict) -> str:
    when = h["time"].strftime("%b %d %H:%M ET") if h.get("time") else "time n/a"
    return f"{h['market']} | {h['source']} | {when} | {h['title']} — {h['summary'][:220]}"


ARROW = {"up": "▲", "down": "▼", "mixed": "◆"}


def _impact_html(s: dict, known: frozenset) -> str:
    markets = [m for m in (s.get("markets") or []) if isinstance(m, str)][:4]
    chips, seen = [], set()
    for imp in (s.get("impact") or [])[:5]:
        if not isinstance(imp, dict):
            continue
        tk = str(imp.get("ticker", "")).upper().strip().replace("$", "")
        if not tk or tk in seen or (known and tk not in known):
            continue  # drop tickers that don't exist
        seen.add(tk)
        d = imp.get("direction") if imp.get("direction") in ARROW else "mixed"
        chips.append(f'<span class="amb-tk"{T.go_attr("t:" + tk)} title="Open {T.esc(tk)} analysis">'
                     f'<span class="ar {d}">{ARROW[d]}</span>{T.esc(tk)}'
                     f'<span class="why">{T.esc(str(imp.get("why", ""))[:60])}</span></span>')
    if not markets and not chips:
        return ""
    mk = "".join(T.chip(m, "plain") for m in markets)
    return (f'<div class="amb-impact"><div class="row" style="margin:0"><b>Moves</b></div>'
            f'<div class="mk">{mk}</div>{"<div class=mk>" + "".join(chips) + "</div>" if chips else ""}</div>')


def _brief(quotes, eww, btc, t10, bx, fix):
    us_news, us_failed = src.recent_headlines("US")
    mx_news, mx_failed = src.recent_headlines("MX")
    pool = us_news[:26] + mx_news[:16]

    T.section("The brief", f"{len(pool)} headlines · refreshed every 6 h", "Written by AI from today's news")
    if not pool:
        T.show('<div class="amb-empty">No headlines came in from the news feeds right now.</div>')
    else:
        waiting = st.empty()
        with waiting.container():
            T.show('<div class="amb-note" style="margin:-4px 0 6px">Top headlines while the brief is written '
                   '(10–30 seconds the first time every 6 hours)…</div>')
            T.show(T.news_list(us_news[:4] + mx_news[:4], 8))
        try:
            with st.spinner("Writing today's brief..."):
                b = ai.daily_brief(_snapshot(quotes, eww, btc, t10, bx, fix),
                                   tuple(_fmt_headline(h) for h in pool), ai.stamp_6h(dt.datetime.now(src.MX)))
            waiting.empty()
            T.show(f'<div class="amb-lead"><span>›</span> {T.esc(b.get("headline", ""))}</div>'
                   f'<div class="amb-grid g2 stack">'
                   f'<div class="amb-take"><div class="h">{T.chip("US", "US")} Wall Street</div><p>{T.esc(b.get("us", ""))}</p></div>'
                   f'<div class="amb-take"><div class="h">{T.chip("MX", "MX")} México</div><p>{T.esc(b.get("mexico", ""))}</p></div>'
                   f'</div>')
            known = src.known_tickers()
            cards = []
            for i, s in enumerate(b.get("stories", []), start=1):
                srcs = "".join(
                    f'<a class="amb-src" href="{T.esc(pool[j]["url"])}" target="_blank" rel="noopener">'
                    f'{T.esc(pool[j]["source"])}{(" · " + pool[j]["time"].strftime("%b %d %H:%M")) if pool[j].get("time") else ""} ↗</a>'
                    for j in s["sources"][:4])
                mk = s.get("market") if s.get("market") in ("US", "MX", "GLOBAL") else "GLOBAL"
                cards.append(
                    f'<div class="amb-story"><div class="top">{T.chip(mk, mk)}<span class="rank">{i:02d}</span></div>'
                    f'<h3>{T.esc(s["title"])}</h3>'
                    f'<div class="row"><b>What happened</b>{T.esc(s.get("what", ""))}</div>'
                    f'<div class="row"><b>Why it matters</b>{T.esc(s.get("why", ""))}</div>'
                    f'{_impact_html(s, known)}'
                    f'<div class="row"><b>Watch next</b>{T.esc(s.get("watch", ""))}</div>'
                    f'<div class="amb-srcs">{srcs}</div></div>')
            st.write("")
            click(T.grid(cards, "g3 stack"), "stories")
            T.show('<div class="amb-note"><span class="amb-tag ai">AI</span>Written by Gemini only from the headlines and numbers '
                   'on this page; every story links to its articles. ▲ ▼ ◆ show the likely first reaction for each ticker '
                   '(up, down, mixed), not a forecast. Click a ticker to analyze it.</div>')
        except Exception as e:
            st.info(f"The AI brief isn't available right now ({e}). The latest headlines are below.")

    with st.expander("All headlines", expanded=False):
        t1, t2 = st.tabs(["Wall Street", "México"])
        with t1:
            T.show(T.news_list(us_news, 25))
        with t2:
            T.show(T.news_list(mx_news, 25))
        failed = us_failed + mx_failed
        if failed:
            T.show(f'<div class="amb-note">Feeds that didn\'t answer this time: {T.esc(", ".join(failed))}</div>')
