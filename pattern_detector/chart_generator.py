"""
Chart Generator
===============
Produces per-pattern candlestick charts with annotations:
  - Pattern trendlines / necklines
  - Entry, Stop, Target levels marked
  - Volume bars
"""
from __future__ import annotations

import os, sys
import warnings
warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as ticker
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from pattern_detector.config import CHART_DIR, SYMBOL

# ── Colour palette ─────────────────────────────────────────────────────────────
BG       = "#0d1117"
PANEL_BG = "#161b22"
GREEN    = "#26a641"
RED      = "#f85149"
GOLD     = "#e3b341"
BLUE     = "#388bfd"
TEXT     = "#c9d1d9"
GRID     = "#21262d"


def _ohlc_to_segments(df_slice: pd.DataFrame):
    """Return wick lines and body rectangles for manual OHLC drawing."""
    xs, wicks, bodies = [], [], []
    for i, (idx, row) in enumerate(df_slice.iterrows()):
        o, h, l, c = row["open"], row["high"], row["low"], row["close"]
        color = GREEN if c >= o else RED
        xs.append(i)
        wicks.append((i, l, h, color))
        bodies.append((i, min(o, c), abs(c - o), color))
    return xs, wicks, bodies


def plot_pattern(df: pd.DataFrame, pattern_row: dict,
                 filename: str | None = None) -> str:
    """
    Generate a candlestick chart for a single pattern.
    Returns the saved filepath.
    """
    start_idx = pattern_row["start_idx"]
    end_idx   = pattern_row["end_idx"]

    # Context: 30 bars before & after the pattern
    ctx = 30
    s = max(0, start_idx - ctx)
    e = min(len(df) - 1, end_idx + ctx)
    df_slice = df.iloc[s: e + 1].reset_index()

    # Map original indices to slice indices
    ps = start_idx - s  # pattern start in slice
    pe = end_idx   - s  # pattern end in slice

    # ── Figure layout ─────────────────────────────────────────────────────────
    fig, (ax_c, ax_v) = plt.subplots(
        2, 1, figsize=(16, 9),
        gridspec_kw={"height_ratios": [4, 1]},
        facecolor=BG
    )
    for ax in (ax_c, ax_v):
        ax.set_facecolor(PANEL_BG)
        ax.tick_params(colors=TEXT, labelsize=7)
        ax.spines[:].set_color(GRID)
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"₹{x:,.0f}"))

    # ── Candlesticks ──────────────────────────────────────────────────────────
    xs, wicks, bodies = _ohlc_to_segments(df_slice)
    for (x, l, h, col) in wicks:
        ax_c.plot([x, x], [l, h], color=col, linewidth=0.8, zorder=2)
    for (x, bot, ht, col) in bodies:
        if ht < 0.01:
            ax_c.plot([x, x], [bot, bot + 0.01], color=col, linewidth=1.5, zorder=3)
        else:
            rect = mpatches.FancyBboxPatch(
                (x - 0.35, bot), 0.7, ht,
                boxstyle="square,pad=0", linewidth=0,
                facecolor=col, zorder=3
            )
            ax_c.add_patch(rect)

    ax_c.set_xlim(-1, len(df_slice) + 1)

    # ── Pattern shading ───────────────────────────────────────────────────────
    ax_c.axvspan(ps, pe, alpha=0.10, color=GOLD, zorder=1)

    # ── Key levels (entry, SL, target) ───────────────────────────────────────
    lvls = {
        "Entry"   : (pattern_row.get("entry"),     BLUE,  "--", 1.5),
        "Stop"    : (pattern_row.get("stop_loss"), RED,   ":",  1.2),
        "Target"  : (pattern_row.get("target"),    GREEN, "--", 1.5),
    }
    for label, (price, color, ls, lw) in lvls.items():
        if price is None:
            continue
        ax_c.axhline(price, color=color, linestyle=ls, linewidth=lw, alpha=0.85, zorder=4)
        ax_c.text(len(df_slice) + 0.5, price, f" {label}\n ₹{price:,.0f}",
                  color=color, fontsize=7.5, va="center", ha="left", zorder=5)

    # ── Key levels from the pattern dict ─────────────────────────────────────
    kl = pattern_row.get("key_levels", {})
    for k, v in kl.items():
        ax_c.axhline(v, color=GOLD, linestyle=":", linewidth=0.9, alpha=0.5)
        ax_c.text(pe, v, f" {k}={v:,.0f}", color=GOLD, fontsize=6.5,
                  va="bottom", ha="left", alpha=0.8)

    # ── Volume bars ───────────────────────────────────────────────────────────
    for i, row in enumerate(df_slice.itertuples()):
        col = GREEN if row.close >= row.open else RED
        ax_v.bar(i, row.volume, color=col, alpha=0.7, width=0.7)

    ax_v.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{x/1e6:.1f}M"))

    # ── X-axis date labels ────────────────────────────────────────────────────
    dates = df_slice["date"] if "date" in df_slice.columns else df_slice.index
    step  = max(1, len(df_slice) // 10)
    ax_c.set_xticks([])
    ax_v.set_xticks(range(0, len(df_slice), step))
    ax_v.set_xticklabels(
        [str(dates.iloc[i])[:16] for i in range(0, len(df_slice), step)],
        rotation=30, fontsize=6, color=TEXT
    )

    # ── Titles ────────────────────────────────────────────────────────────────
    direction_icon = "🟢" if pattern_row["direction"] == "bullish" else "🔴"
    fig.suptitle(
        f"{direction_icon}  {SYMBOL} — {pattern_row['pattern']}  "
        f"({pattern_row['direction'].upper()})\n"
        f"Entry: ₹{pattern_row.get('entry',0):,.0f}  "
        f"SL: ₹{pattern_row.get('stop_loss',0):,.0f}  "
        f"Target: ₹{pattern_row.get('target',0):,.0f}  "
        f"R:R = {pattern_row.get('risk_reward',0):.1f}x  "
        f"Confidence: {pattern_row.get('confidence',0):.0%}",
        color=TEXT, fontsize=10, y=0.98
    )
    ax_c.grid(True, color=GRID, linewidth=0.5, alpha=0.7)
    ax_v.grid(True, color=GRID, linewidth=0.5, alpha=0.5, axis="y")

    plt.tight_layout(rect=[0, 0, 0.93, 0.96])

    # ── Save ──────────────────────────────────────────────────────────────────
    if filename is None:
        safe_name = pattern_row["pattern"].replace(" ", "_").replace("/", "_")
        filename = os.path.join(CHART_DIR, f"{safe_name}_{start_idx}.png")

    plt.savefig(filename, dpi=120, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    return filename


def generate_all_charts(df: pd.DataFrame, patterns_df: pd.DataFrame,
                        max_charts: int = 30) -> dict[str, str]:
    """
    Generate charts for all (or top N) patterns.
    Returns {trade_id → chart_path}.
    """
    charts = {}
    rows = patterns_df.head(max_charts)
    total = len(rows)

    for i, (_, row) in enumerate(rows.iterrows(), 1):
        try:
            tid = row.get("trade_id", f"T{i:04d}")
            safe_patt = str(row["pattern"]).replace(" ", "_").replace("/", "_")
            fname = os.path.join(CHART_DIR, f"{tid}_{safe_patt}.png")
            chart = plot_pattern(df, row.to_dict(), fname)
            charts[str(tid)] = chart
            print(f"  Chart {i}/{total}: {fname}")
        except Exception as exc:
            print(f"  Chart {i}/{total}: ERROR – {exc}")

    return charts
