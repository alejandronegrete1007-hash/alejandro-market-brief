"""PDF downloads: the research note of a stock and the portfolio report.

Built with fpdf2 and the app's two typefaces (Spectral for titles and figures, Inter Tight for text),
on white paper so they print well. Charts are drawn with matplotlib.
"""
from __future__ import annotations

import io
import os
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from fpdf import FPDF  # noqa: E402
from fpdf.fonts import FontFace  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "assets", "fonts")
INK, MUTED, RULE, ACC, UP, DOWN = (24, 27, 33), (110, 116, 126), (214, 217, 222), (47, 84, 196), (46, 125, 84), (176, 58, 52)
_SAFE = {"−": "-", "–": "-", "—": " - ", "≈": "~", "×": "x", "→": "->", "▲": "+", "▼": "-", "◆": "*", "≥": ">=", "≤": "<=",
         " ": " ", " ": " ", "…": "...", "‘": "'", "’": "'", "“": '"', "”": '"', "•": "-"}


def _t(text) -> str:
    """Text the embedded fonts can draw (they carry Latin-1, so a few typographic symbols are swapped)."""
    s = str(text if text is not None else "")
    for a, b in _SAFE.items():
        s = s.replace(a, b)
    return re.sub(r"[^\x00-\xff]", "", s)


class Doc(FPDF):
    def __init__(self, title: str, subtitle: str):
        super().__init__(format="Letter", unit="mm")
        self.add_font("Spectral", "", os.path.join(FONTS, "Spectral-Medium.ttf"))
        self.add_font("Inter", "", os.path.join(FONTS, "InterTight-Regular.ttf"))
        self.add_font("Inter", "B", os.path.join(FONTS, "InterTight-SemiBold.ttf"))
        self.set_margins(18, 16, 18)
        self.set_auto_page_break(True, 16)
        self.doc_title, self.doc_sub = _t(title), _t(subtitle)
        self.add_page()

    def header(self):
        self.set_font("Inter", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 5, "Alejandro Market Brief", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*RULE)
        self.line(self.l_margin, self.get_y() + 1, self.w - self.r_margin, self.get_y() + 1)
        self.ln(4)

    def footer(self):
        self.set_y(-12)
        self.set_font("Inter", "", 7.5)
        self.set_text_color(*MUTED)
        self.cell(0, 5, _t(f"{self.doc_sub}   ·   page {self.page_no()}   ·   Not investment advice"), align="R")

    # ---- building blocks
    def title_block(self, title: str, lines: list[str]):
        self.set_font("Spectral", "", 24)
        self.set_text_color(*INK)
        self.multi_cell(0, 10, _t(title), new_x="LMARGIN", new_y="NEXT")
        self.set_font("Inter", "", 9.5)
        self.set_text_color(*MUTED)
        for ln in lines:
            self.multi_cell(0, 5, _t(ln), new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

    def ensure(self, mm: float):
        """Start a new page unless `mm` of space is left (keeps a heading with what follows it)."""
        if self.get_y() + mm > self.h - 18:
            self.add_page()

    def h2(self, text: str, keep: float = 28):
        self.ensure(keep)
        self.ln(2)
        self.set_font("Spectral", "", 14)
        self.set_text_color(*INK)
        self.cell(0, 7, _t(text), new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*RULE)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2.5)

    def para(self, text: str, size: float = 10, color=INK, bold: bool = False):
        if not text:
            return
        self.set_font("Inter", "B" if bold else "", size)
        self.set_text_color(*color)
        self.multi_cell(0, size * 0.5, _t(text), new_x="LMARGIN", new_y="NEXT")
        self.ln(1.5)

    def bullets(self, items, numbered: bool = False):
        self.set_font("Inter", "", 10)
        self.set_text_color(*INK)
        for i, it in enumerate(items or [], start=1):
            mark = f"{i}." if numbered else "-"
            x = self.get_x()
            self.cell(6, 5, mark)
            self.multi_cell(0, 5, _t(re.sub(r"^\s*(\d+[.)]|[-•*])\s*", "", str(it))), new_x="LMARGIN", new_y="NEXT")
            self.set_x(x)
            self.ln(0.8)
        self.ln(1)

    def metrics(self, items: list[tuple[str, str]], cols: int = 3):
        """Key figures in a grid: small label, big number."""
        w = (self.w - self.l_margin - self.r_margin) / cols
        for i in range(0, len(items), cols):
            row = items[i:i + cols]
            y = self.get_y()
            for j, (k, v) in enumerate(row):
                x = self.l_margin + j * w
                self.set_xy(x, y)
                self.set_font("Inter", "", 7.5)
                self.set_text_color(*MUTED)
                self.cell(w - 3, 4, _t(k))
                self.set_xy(x, y + 4.2)
                self.set_font("Spectral", "", 14)
                self.set_text_color(*INK)
                self.cell(w - 3, 7, _t(v))
            self.set_y(y + 13)
        self.ln(1)

    def grid_table(self, head: list[str], rows: list[list[str]], widths: list[float] | None = None, bold_last: bool = False,
              colors: list[list] | None = None):
        self.set_font("Inter", "", 8.5)
        self.set_text_color(*INK)
        self.set_draw_color(*RULE)
        style = FontFace(family="Inter", emphasis="B", color=MUTED, size_pt=7.5)
        with self.table(col_widths=widths, text_align=["LEFT"] + ["RIGHT"] * (len(head) - 1), headings_style=style,
                        borders_layout="HORIZONTAL_LINES", line_height=5.6, padding=1.2) as tbl:
            tbl.row([_t(h) for h in head])
            for i, r in enumerate(rows):
                last = bold_last and i == len(rows) - 1
                row = tbl.row()
                for j, cell in enumerate(r):
                    c = colors[i][j] if colors and colors[i] and colors[i][j] else INK
                    row.cell(_t(cell), style=FontFace(family="Inter", emphasis="B" if last else "", color=c, size_pt=8.5))
        self.ln(3)

    def image_png(self, png: bytes, height: float = 62):
        if self.get_y() + height > self.h - 18:
            self.add_page()
        self.image(io.BytesIO(png), x=self.l_margin, w=self.w - self.l_margin - self.r_margin, h=height)
        self.ln(2)

    def output_bytes(self) -> bytes:
        return bytes(self.output())


def tone_color(x) -> tuple | None:
    if x is None:
        return None
    try:
        return UP if float(x) > 0 else DOWN if float(x) < 0 else None
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- charts
def _style(ax):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#C9CDD3")
    ax.tick_params(colors="#5F6670", labelsize=8)
    ax.grid(axis="y", color="#E6E8EB", linewidth=0.6)
    ax.set_axisbelow(True)


def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def line_chart(series: dict, ylabel: str = "%") -> bytes:
    """series: name -> (dates, values in %)."""
    fig, ax = plt.subplots(figsize=(7.2, 2.7))
    colors = ["#2F54C4", "#8A9099", "#B08D57"]
    for (name, (x, y)), c in zip(series.items(), colors):
        ax.plot(x, y, label=name, color=c, linewidth=1.8 if c == colors[0] else 1.2, linestyle="-" if c == colors[0] else "--")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0f}{ylabel}"))
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    _style(ax)
    return _png(fig)


def _money(v: float) -> str:
    return f"{'-' if v < 0 else ''}${abs(v):,.0f}"


def bar_chart(labels: list[str], values: list[float], fmt=_money) -> bytes:
    fig, ax = plt.subplots(figsize=(7.2, max(1.6, 0.36 * len(labels) + 0.6)))
    colors = ["#2E7D54" if v >= 0 else "#B03A34" for v in values]
    ax.barh(labels, values, color=colors, height=0.6)
    for i, v in enumerate(values):
        ax.text(v, i, " " + fmt(v) + " ", va="center", ha="left" if v >= 0 else "right", fontsize=7.5, color="#3A3F47")
    ax.axvline(0, color="#C9CDD3", linewidth=0.8)
    ax.invert_yaxis()
    _style(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color="#E6E8EB", linewidth=0.6)
    lo, hi = min(values + [0]), max(values + [0])
    pad = (hi - lo) * 0.25 or 1
    ax.set_xlim(lo - (pad if lo < 0 else 0), hi + pad)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: fmt(v)))
    return _png(fig)
