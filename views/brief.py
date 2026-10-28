"""Today: both markets at a glance and the AI-written daily brief."""
from __future__ import annotations

import datetime as dt

import streamlit as st

import ai
import mexico
import sources as src
import state
import theme as T
from views.common import analyze_picker, mini_rows

US_SET = [("S&P 500", "SPY"), ("Nasdaq 100", "QQQ"), ("Dow Jones", "DIA"), ("Russell 2000", "IWM"),
          ("Gold", "GLD"), ("Oil · WTI", "USO")]


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception:
        return None


def _etf_tile(label, sym, q, is_open):
    if not q:
        return T.tile(label, "—", T.chip(sym, "US"), "unavailable", accent="us")
    return T.tile(
        label, T.money(q["price"]), T.pill(q["pct"]),
        f"{sym} · {T.clock(q['time'])}", T.freshness(q["time"], is_open),
        T.range_bar(q["low"], q["high"], q["price"], "L", "H"), accent="us")


def _hero(status):
    now_et, now_mx = dt.datetime.now(src.ET), dt.datetime.now(src.MX)
    us = '<span class="amb-dot on"></span>NYSE open' if status["open"] else '<span class="amb-dot off"></span>NYSE closed · latest close'
    bmv = '<span class="amb-dot on"></span>BMV open' if src.bmv_open() else '<span class="amb-dot off"></span>BMV closed'
    T.show(f"""
    <div class="amb-hero">
      <div><div class="amb-kicker">Daily brief · Wall Street &amp; México</div>
        <h1>{now_mx:%A, %B} {now_mx.day}</h1>
        <div class="sub"><span>{us}</span><span>{bmv}</span></div></div>
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

    # ticker tape
    items = [(lbl, T.money(q["price"]), q["pct"]) for (lbl, s), q in ((x, quotes[x[1]]) for x in US_SET) if q]
    if btc:
        items.append(("Bitcoin", T.money(btc["price"]), btc["pct"]))
    if fix is not None and len(fix) > 1:
        items.append(("USD/MXN", f"{fix.iloc[-1]:.4f}", (fix.iloc[-1] / fix.iloc[-2] - 1) * 100))
    if eww:
        items.append(("México · EWW", T.money(eww["price"]), eww["pct"]))
    if t10 is not None:
        items.append(("US 10Y", f"{t10.iloc[-1]:.2f}%", None))
    if S["target"] in bx:
        items.append(("Banxico rate", f"{bx[S['target']]['value']:.2f}%", None))
    if items:
        T.show(T.tape(items))

    main, rail = st.columns([2.9, 1], gap="large")
    with main:
        # ---------------- Wall Street
        T.section("Wall Street", "ETF proxies for the indices", T.chip("US", "US"))
        tiles = [_etf_tile(l, s, quotes[s], is_open) for l, s in US_SET[:4]]
        T.show(T.grid(tiles))
        tiles = [_etf_tile(l, s, quotes[s], is_open) for l, s in US_SET[4:]]
        if btc:
            tiles.append(T.tile("Bitcoin", T.money(btc["price"], 0), T.pill(btc["pct"], suffix=" 24h"),
                                f"CoinGecko · {T.clock(btc['time'])}", T.chip("24/7", "live"), accent="us"))
        if t10 is not None and len(t10) > 1:
            bps = (t10.iloc[-1] - t10.iloc[-2]) * 100
            tiles.append(T.tile("US 10-year yield", f"{t10.iloc[-1]:.2f}%",
                                f'<span class="amb-pill {T.tone(bps)}">{bps:+.0f} bps</span>',
                                f"FRED · {t10.index[-1]:%b %d}", T.chip("daily", "daily"),
                                f'<div class="spark">{T.spark(t10.iloc[-120:], color=T.C["gold"])}</div>', accent="us"))
        T.show(T.grid(tiles))

        # ---------------- Mexico
        T.section("México", "Banxico SIE · NYSE-listed ADRs", T.chip("MX", "MX"))
        tiles = []
        if fix is not None and len(fix) > 1:
            chg = (fix.iloc[-1] / fix.iloc[-2] - 1) * 100
            ytd_base = fix[fix.index < dt.datetime(fix.index[-1].year, 1, 1)]
            ytd = (fix.iloc[-1] / ytd_base.iloc[-1] - 1) * 100 if len(ytd_base) else None
            tiles.append(T.tile("Dollar in pesos (FIX)", f"{fix.iloc[-1]:.4f}", T.pill(chg),
                                f"Banxico · {fix.index[-1]:%b %d}" + (f" · YTD {T.pct(ytd, 1, frac=False)}" if ytd is not None else ""),
                                T.chip("daily", "daily"),
                                f'<div class="spark">{T.spark(fix.iloc[-90:], color=T.C["mx"])}</div>', accent="mx"))
        if eww:
            tiles.append(T.tile("Mexican stocks (EWW)", T.money(eww["price"]), T.pill(eww["pct"]),
                                f"MSCI Mexico · {T.clock(eww['time'])}", T.freshness(eww["time"], is_open),
                                T.range_bar(eww["low"], eww["high"], eww["price"], "L", "H"), accent="mx"))
        if S["target"] in bx:
            b = bx[S["target"]]
            carry = ""
            if fed is not None:
                carry = f'<div class="amb-note" style="margin-top:4px">Spread vs Fed (upper): <b style="color:var(--text)">{b["value"] - fed.iloc[-1]:+.2f} pts</b></div>'
            tiles.append(T.tile("Banxico target rate", f"{b['value']:.2f}%", "", f"Banxico · {b['date']:%b %d}",
                                T.chip("official", "daily"), carry, accent="mx"))
        if S["cetes28"] in bx:
            b = bx[S["cetes28"]]
            tiles.append(T.tile("CETES 28 days", f"{b['value']:.2f}%", "", f"Auction · {b['date']:%b %d}",
                                T.chip("weekly", "daily"), accent="mx"))
        if S["inflation"] in bx:
            b = bx[S["inflation"]]
            inside = abs(b["value"] - mexico.INFLATION_TARGET) <= 1
            flag = T.chip("in band" if inside else "above band" if b["value"] > 4 else "below band",
                          "live" if inside else "delayed")
            tiles.append(T.tile("Inflation, annual", f"{b['value']:.2f}%", flag,
                                f"INPC · {b['date']:%b %Y}", T.chip("monthly", "daily"),
                                T.range_bar(1.5, 6.0, b["value"], "", "", fmt=lambda v: f"{v:.1f}%"), accent="mx"))
        if S["tiie28"] in bx:
            b = bx[S["tiie28"]]
            tiles.append(T.tile("TIIE 28 days", f"{b['value']:.2f}%", "", f"Banxico · {b['date']:%b %d}",
                                T.chip("daily", "daily"), accent="mx"))
        if S["target"] in bx and S["inflation"] in bx:
            real = bx[S["target"]]["value"] - bx[S["inflation"]]["value"]
            tiles.append(T.tile("Real policy rate", f"{real:.2f}%", "",
                                "Banxico rate − inflation", T.chip("calc", "daily"),
                                '<div class="amb-note" style="margin-top:4px">Above ~2% is a tight stance</div>', accent="mx"))
        lead = _safe(mexico.leaderboard)
        if lead and lead[0]["ytd"] is not None:
            r = lead[0]
            tiles.append(T.tile("Top Mexican ADR, YTD", T.esc(r["symbol"]), T.pill(r["ytd"] * 100),
                                T.esc(r["name"][:22]), T.chip("ytd", "daily"), accent="mx"))
        if tiles:
            T.show(T.grid(tiles))
        else:
            T.show('<div class="amb-empty">Mexico data unavailable. Check BANXICO_TOKEN in Secrets.</div>')

        brief_slot = st.container()

    with rail:
        T.section("Your watchlist")
        T.show(f'<div class="amb-note" style="margin:-6px 0 8px">{T.chip("US", "US")} S&amp;P 500 picks</div>')
        T.show(mini_rows(st.session_state.wl_us))
        mx_syms, live = state.mx_list()
        T.show(f'<div class="amb-note" style="margin:16px 0 8px">{T.chip("MX", "MX")} '
               f'{"Top 5 Mexican ADRs, YTD" if live else "Mexican picks"}</div>')
        T.show(mini_rows(mx_syms))
        st.write("")
        analyze_picker(st.session_state.wl_us + mx_syms, "pick_home", "Analyze a stock")

    with brief_slot:
        _brief(quotes, eww, btc, t10, bx, fix, status)
    T.footer("Not investment advice · data from Finnhub, Twelve Data, FRED, Banxico, SEC, CoinGecko")


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
        lines.append(f"USD/MXN FIX: {fix.iloc[-1]:.4f} ({(fix.iloc[-1] / fix.iloc[-2] - 1) * 100:+.2f}%; a higher number means a weaker peso)")
    if eww:
        lines.append(f"Mexican stocks via EWW ETF: {eww['price']:.2f} ({eww['pct']:+.2f}%)")
    labels = {"target": "Banxico target rate", "cetes28": "CETES 28-day yield", "tiie28": "TIIE 28",
              "inflation": "Mexico annual inflation"}
    for k, lbl in labels.items():
        b = bx.get(mexico.SERIES[k])
        if b:
            lines.append(f"{lbl}: {b['value']:.2f}% (as of {b['date']})")
    return "\n".join(lines)


def _fmt_headline(h: dict) -> str:
    when = h["time"].strftime("%b %d %H:%M ET") if h.get("time") else "time n/a"
    return f"{h['market']} | {h['source']} | {when} | {h['title']} — {h['summary'][:220]}"


def _brief(quotes, eww, btc, t10, bx, fix, status):
    us_news, us_failed = src.recent_headlines("US")
    mx_news, mx_failed = src.recent_headlines("MX")
    pool = us_news[:26] + mx_news[:16]

    T.section("The brief", f"{len(pool)} headlines · AI summary refreshes every 6 h")
    if not pool:
        T.show('<div class="amb-empty">No headlines came in from the news feeds right now.</div>')
    else:
        try:
            with st.spinner("Writing today's brief..."):
                now = dt.datetime.now(src.MX)
                b = ai.daily_brief(_snapshot(quotes, eww, btc, t10, bx, fix),
                                   tuple(_fmt_headline(h) for h in pool), ai.stamp_6h(now))
            lead = T.esc(b.get("headline", ""))
            T.show(f'<div class="amb-lead"><span>›</span> {lead}</div>'
                   f'<div class="amb-brief">'
                   f'<div class="amb-take"><div class="h">{T.chip("US", "US")} Wall Street</div><p>{T.esc(b.get("us", ""))}</p></div>'
                   f'<div class="amb-take"><div class="h">{T.chip("MX", "MX")} México</div><p>{T.esc(b.get("mexico", ""))}</p></div>'
                   f'</div>')
            cards = []
            for i, s in enumerate(b.get("stories", []), start=1):
                srcs = "".join(
                    f'<a class="amb-src" href="{T.esc(pool[j]["url"])}" target="_blank" rel="noopener">'
                    f'{T.esc(pool[j]["source"])}{(" · " + pool[j]["time"].strftime("%b %d %H:%M")) if pool[j].get("time") else ""}</a>'
                    for j in s["sources"][:4])
                mk = s.get("market", "GLOBAL") if s.get("market") in ("US", "MX", "GLOBAL") else "GLOBAL"
                cards.append(
                    f'<div class="amb-story"><div class="top">{T.chip(mk, mk)}<span class="rank">{i:02d}</span></div>'
                    f'<h3>{T.esc(s["title"])}</h3>'
                    f'<div class="row"><b>What happened</b>{T.esc(s.get("what", ""))}</div>'
                    f'<div class="row"><b>Why it matters</b>{T.esc(s.get("why", ""))}</div>'
                    f'<div class="row"><b>Watch next</b>{T.esc(s.get("watch", ""))}</div>'
                    f'<div class="amb-srcs">{srcs}</div></div>')
            st.write("")
            T.show(T.grid(cards, "g3"))
            T.show('<div class="amb-note"><span class="amb-tag ai">AI</span>Written by Gemini from the headlines and '
                   'numbers above only. Every story links to the articles it is based on.</div>')
        except Exception as e:
            st.info(f"The AI brief isn't available right now ({e}). Latest headlines below.")

    with st.expander("All headlines", expanded=False):
        t1, t2 = st.tabs(["Wall Street", "México"])
        with t1:
            T.show(T.news_list(us_news, 25))
        with t2:
            T.show(T.news_list(mx_news, 25))
        failed = us_failed + mx_failed
        if failed:
            T.show(f'<div class="amb-note">Feeds that didn\'t answer this time: {T.esc(", ".join(failed))}</div>')
