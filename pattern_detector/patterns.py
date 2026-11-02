"""
Pattern Detectors
=================
Implements ALL patterns from TheChartGuys cheat sheet:

Reversal Patterns:
  1.  Head & Shoulders (bearish)
  2.  Inverse Head & Shoulders (bullish)
  3.  Double Top
  4.  Double Bottom
  5.  Triple Top
  6.  Triple Bottom
  7.  Rising Wedge  (bearish reversal / continuation)
  8.  Falling Wedge (bullish reversal / continuation)

Continuation Patterns:
  9.  Bull Flag
  10. Bear Flag
  11. Bull Pennant
  12. Bear Pennant
  13. Ascending Triangle
  14. Descending Triangle
  15. Symmetrical Triangle
  16. Ascending Channel (Bull Channel)
  17. Descending Channel (Bear Channel)
  18. Cup and Handle

Each detector returns a list of dicts:
  {
    "pattern"       : <str>,
    "direction"     : "bullish" | "bearish",
    "type"          : "reversal" | "continuation",
    "start_idx"     : <int>,     # bar index in df
    "end_idx"       : <int>,
    "start_date"    : <Timestamp>,
    "end_date"      : <Timestamp>,
    "key_levels"    : {<name>: <price>},
    "entry"         : <float>,
    "stop_loss"     : <float>,
    "target"        : <float>,
    "risk_reward"   : <float>,
    "confidence"    : <float>,   # 0-1
    "notes"         : <str>,
  }
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from typing import List, Dict, Any

from pattern_detector.utils import (
    find_swing_highs, find_swing_lows,
    prices_approx_equal, pct_diff,
    fit_trendline, volume_spike, atr,
    rolling_slope
)
from pattern_detector.config import (
    PIVOT_WINDOW, PRICE_TOLERANCE_PCT,
    MIN_PATTERN_DEPTH_PCT, SL_BUFFER_PCT,
    DEFAULT_RISK_REWARD, VOLUME_CONFIRM, VOLUME_MULT
)

PatternList = List[Dict[str, Any]]

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _trade_levels(direction: str, key: float, neckline: float,
                  pattern_range: float, df: pd.DataFrame,
                  end_idx: int) -> Dict[str, float]:
    """
    Generic trade level calculator.
    direction: 'bullish' → buy breakout, 'bearish' → sell breakout
    key       : breakout price (neckline / support / resistance)
    neckline  : same as key in most patterns
    pattern_range: height of the pattern (for target projection)
    """
    buf = key * SL_BUFFER_PCT
    atr_val = atr(df).iloc[end_idx] if not np.isnan(atr(df).iloc[end_idx]) else buf * 5

    if direction == "bullish":
        entry   = key + buf              # buy on breakout
        stop    = key - max(buf * 3, atr_val * 0.5)
        target  = entry + pattern_range
    else:
        entry   = key - buf              # sell on breakdown
        stop    = key + max(buf * 3, atr_val * 0.5)
        target  = entry - pattern_range

    risk = abs(entry - stop)
    reward = abs(target - entry)
    rr = round(reward / risk, 2) if risk > 0 else 0.0

    return {
        "entry"       : round(entry, 2),
        "stop_loss"   : round(stop,  2),
        "target"      : round(target, 2),
        "risk_reward" : rr,
    }


def _base_pattern(pattern: str, direction: str, ptype: str,
                  start_idx: int, end_idx: int,
                  df: pd.DataFrame, key_levels: dict,
                  trade: dict, confidence: float, notes: str) -> dict:
    return {
        "pattern"    : pattern,
        "direction"  : direction,
        "type"       : ptype,
        "start_idx"  : start_idx,
        "end_idx"    : end_idx,
        "start_date" : df.index[start_idx],
        "end_date"   : df.index[end_idx],
        "key_levels" : key_levels,
        **trade,
        "confidence" : round(confidence, 3),
        "notes"      : notes,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1 & 2. HEAD AND SHOULDERS / INVERSE HEAD AND SHOULDERS
# ─────────────────────────────────────────────────────────────────────────────

def detect_head_and_shoulders(df: pd.DataFrame) -> PatternList:
    """Detect both Head & Shoulders (bearish) and Inverse H&S (bullish)."""
    results: PatternList = []
    sh  = find_swing_highs(df, PIVOT_WINDOW)
    sl  = find_swing_lows(df,  PIVOT_WINDOW)
    tol = PRICE_TOLERANCE_PCT

    # ── Bearish H&S ───────────────────────────────────────────────────────────
    for i in range(len(sh) - 2):
        ls_idx, h_idx, rs_idx = sh[i], sh[i + 1], sh[i + 2]
        ls = df["high"].iloc[ls_idx]
        hd = df["high"].iloc[h_idx]
        rs = df["high"].iloc[rs_idx]

        if hd <= ls or hd <= rs:
            continue
        if not prices_approx_equal(ls, rs, tol * 2):
            continue

        depth = (hd - min(ls, rs)) / hd
        if depth < MIN_PATTERN_DEPTH_PCT:
            continue

        # neckline = avg of the two troughs between shoulders
        troughs = [i for i in sl if ls_idx < i < rs_idx]
        if len(troughs) < 2:
            continue
        t1 = df["low"].iloc[troughs[0]]
        t2 = df["low"].iloc[troughs[-1]]
        neckline = (t1 + t2) / 2

        pattern_range = hd - neckline
        trade = _trade_levels("bearish", neckline, neckline, pattern_range, df, rs_idx)
        if trade["risk_reward"] < DEFAULT_RISK_REWARD:
            continue

        vol_ok = not VOLUME_CONFIRM or volume_spike(df, rs_idx, mult=VOLUME_MULT)
        conf = 0.5 + 0.2 * vol_ok + 0.15 * (depth > 0.02) + 0.15 * prices_approx_equal(ls, rs, tol)

        results.append(_base_pattern(
            "Head & Shoulders", "bearish", "reversal",
            ls_idx, rs_idx, df,
            {"left_shoulder": round(ls,2), "head": round(hd,2),
             "right_shoulder": round(rs,2), "neckline": round(neckline,2)},
            trade, conf,
            f"Depth={depth:.1%}, L.Shoulder≈R.Shoulder tol={tol:.1%}, neckline={neckline:.0f}"
        ))

    # ── Bullish Inverse H&S ───────────────────────────────────────────────────
    for i in range(len(sl) - 2):
        ls_idx, h_idx, rs_idx = sl[i], sl[i + 1], sl[i + 2]
        ls = df["low"].iloc[ls_idx]
        hd = df["low"].iloc[h_idx]
        rs = df["low"].iloc[rs_idx]

        if hd >= ls or hd >= rs:
            continue
        if not prices_approx_equal(ls, rs, tol * 2):
            continue

        depth = (max(ls, rs) - hd) / hd
        if depth < MIN_PATTERN_DEPTH_PCT:
            continue

        peaks = [i for i in sh if ls_idx < i < rs_idx]
        if len(peaks) < 2:
            continue
        p1 = df["high"].iloc[peaks[0]]
        p2 = df["high"].iloc[peaks[-1]]
        neckline = (p1 + p2) / 2

        pattern_range = neckline - hd
        trade = _trade_levels("bullish", neckline, neckline, pattern_range, df, rs_idx)
        if trade["risk_reward"] < DEFAULT_RISK_REWARD:
            continue

        vol_ok = not VOLUME_CONFIRM or volume_spike(df, rs_idx, mult=VOLUME_MULT)
        conf = 0.5 + 0.2 * vol_ok + 0.15 * (depth > 0.02) + 0.15 * prices_approx_equal(ls, rs, tol)

        results.append(_base_pattern(
            "Inverse Head & Shoulders", "bullish", "reversal",
            ls_idx, rs_idx, df,
            {"left_shoulder": round(ls,2), "head": round(hd,2),
             "right_shoulder": round(rs,2), "neckline": round(neckline,2)},
            trade, conf,
            f"Depth={depth:.1%}, neckline={neckline:.0f}"
        ))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# 3 & 4. DOUBLE TOP / DOUBLE BOTTOM
# ─────────────────────────────────────────────────────────────────────────────

def detect_double_top_bottom(df: pd.DataFrame) -> PatternList:
    results: PatternList = []
    sh  = find_swing_highs(df, PIVOT_WINDOW)
    sl  = find_swing_lows(df,  PIVOT_WINDOW)
    tol = PRICE_TOLERANCE_PCT

    # ── Double Top ────────────────────────────────────────────────────────────
    for i in range(len(sh) - 1):
        p1_idx, p2_idx = sh[i], sh[i + 1]
        p1, p2 = df["high"].iloc[p1_idx], df["high"].iloc[p2_idx]

        if not prices_approx_equal(p1, p2, tol * 2):
            continue
        gap = p2_idx - p1_idx
        if gap < PIVOT_WINDOW * 2:
            continue

        troughs = [j for j in sl if p1_idx < j < p2_idx]
        if not troughs:
            continue
        valley_idx = min(troughs, key=lambda j: df["low"].iloc[j])
        valley = df["low"].iloc[valley_idx]
        neckline = valley

        depth = (max(p1, p2) - valley) / max(p1, p2)
        if depth < MIN_PATTERN_DEPTH_PCT:
            continue

        pattern_range = max(p1, p2) - valley
        trade = _trade_levels("bearish", neckline, neckline, pattern_range, df, p2_idx)
        if trade["risk_reward"] < DEFAULT_RISK_REWARD:
            continue

        vol_ok = not VOLUME_CONFIRM or volume_spike(df, p2_idx, mult=VOLUME_MULT)
        conf = 0.45 + 0.2 * vol_ok + 0.2 * (depth > 0.015) + 0.15 * prices_approx_equal(p1, p2, tol)

        results.append(_base_pattern(
            "Double Top", "bearish", "reversal",
            p1_idx, p2_idx, df,
            {"peak1": round(p1,2), "peak2": round(p2,2), "neckline": round(neckline,2)},
            trade, conf,
            f"Peak diff={pct_diff(p1,p2):.2%}, depth={depth:.1%}"
        ))

    # ── Double Bottom ─────────────────────────────────────────────────────────
    for i in range(len(sl) - 1):
        b1_idx, b2_idx = sl[i], sl[i + 1]
        b1, b2 = df["low"].iloc[b1_idx], df["low"].iloc[b2_idx]

        if not prices_approx_equal(b1, b2, tol * 2):
            continue
        gap = b2_idx - b1_idx
        if gap < PIVOT_WINDOW * 2:
            continue

        peaks = [j for j in sh if b1_idx < j < b2_idx]
        if not peaks:
            continue
        peak_idx = max(peaks, key=lambda j: df["high"].iloc[j])
        neckline = df["high"].iloc[peak_idx]

        depth = (neckline - min(b1, b2)) / neckline
        if depth < MIN_PATTERN_DEPTH_PCT:
            continue

        pattern_range = neckline - min(b1, b2)
        trade = _trade_levels("bullish", neckline, neckline, pattern_range, df, b2_idx)
        if trade["risk_reward"] < DEFAULT_RISK_REWARD:
            continue

        vol_ok = not VOLUME_CONFIRM or volume_spike(df, b2_idx, mult=VOLUME_MULT)
        conf = 0.45 + 0.2 * vol_ok + 0.2 * (depth > 0.015) + 0.15 * prices_approx_equal(b1, b2, tol)

        results.append(_base_pattern(
            "Double Bottom", "bullish", "reversal",
            b1_idx, b2_idx, df,
            {"bottom1": round(b1,2), "bottom2": round(b2,2), "neckline": round(neckline,2)},
            trade, conf,
            f"Bottom diff={pct_diff(b1,b2):.2%}, depth={depth:.1%}"
        ))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# 5 & 6. TRIPLE TOP / TRIPLE BOTTOM
# ─────────────────────────────────────────────────────────────────────────────

def detect_triple_top_bottom(df: pd.DataFrame) -> PatternList:
    results: PatternList = []
    sh  = find_swing_highs(df, PIVOT_WINDOW)
    sl  = find_swing_lows(df,  PIVOT_WINDOW)
    tol = PRICE_TOLERANCE_PCT * 1.5  # slightly looser for 3 touches

    # ── Triple Top ────────────────────────────────────────────────────────────
    for i in range(len(sh) - 2):
        p1_idx, p2_idx, p3_idx = sh[i], sh[i + 1], sh[i + 2]
        p1 = df["high"].iloc[p1_idx]
        p2 = df["high"].iloc[p2_idx]
        p3 = df["high"].iloc[p3_idx]

        if not (prices_approx_equal(p1, p2, tol) and
                prices_approx_equal(p2, p3, tol) and
                prices_approx_equal(p1, p3, tol)):
            continue

        depth = (max(p1,p2,p3) - df["low"].iloc[p1_idx:p3_idx+1].min()) / max(p1,p2,p3)
        if depth < MIN_PATTERN_DEPTH_PCT:
            continue

        neckline = df["low"].iloc[p1_idx:p3_idx+1].min()
        pattern_range = max(p1,p2,p3) - neckline
        trade = _trade_levels("bearish", neckline, neckline, pattern_range, df, p3_idx)
        if trade["risk_reward"] < DEFAULT_RISK_REWARD:
            continue

        conf = 0.55 + 0.2 * (depth > 0.02) + 0.15 * prices_approx_equal(p1, p3, tol * 0.5)

        results.append(_base_pattern(
            "Triple Top", "bearish", "reversal",
            p1_idx, p3_idx, df,
            {"peak1": round(p1,2), "peak2": round(p2,2), "peak3": round(p3,2),
             "neckline": round(neckline,2)},
            trade, conf, f"3 touches near {max(p1,p2,p3):.0f}, depth={depth:.1%}"
        ))

    # ── Triple Bottom ─────────────────────────────────────────────────────────
    for i in range(len(sl) - 2):
        b1_idx, b2_idx, b3_idx = sl[i], sl[i + 1], sl[i + 2]
        b1 = df["low"].iloc[b1_idx]
        b2 = df["low"].iloc[b2_idx]
        b3 = df["low"].iloc[b3_idx]

        if not (prices_approx_equal(b1, b2, tol) and
                prices_approx_equal(b2, b3, tol) and
                prices_approx_equal(b1, b3, tol)):
            continue

        depth = (df["high"].iloc[b1_idx:b3_idx+1].max() - min(b1,b2,b3)) / df["high"].iloc[b1_idx:b3_idx+1].max()
        if depth < MIN_PATTERN_DEPTH_PCT:
            continue

        neckline = df["high"].iloc[b1_idx:b3_idx+1].max()
        pattern_range = neckline - min(b1,b2,b3)
        trade = _trade_levels("bullish", neckline, neckline, pattern_range, df, b3_idx)
        if trade["risk_reward"] < DEFAULT_RISK_REWARD:
            continue

        conf = 0.55 + 0.2 * (depth > 0.02) + 0.15 * prices_approx_equal(b1, b3, tol * 0.5)

        results.append(_base_pattern(
            "Triple Bottom", "bullish", "reversal",
            b1_idx, b3_idx, df,
            {"bottom1": round(b1,2), "bottom2": round(b2,2), "bottom3": round(b3,2),
             "neckline": round(neckline,2)},
            trade, conf, f"3 touches near {min(b1,b2,b3):.0f}, depth={depth:.1%}"
        ))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# 7 & 8. RISING WEDGE / FALLING WEDGE
# ─────────────────────────────────────────────────────────────────────────────

def detect_wedges(df: pd.DataFrame) -> PatternList:
    results: PatternList = []
    sh = find_swing_highs(df, PIVOT_WINDOW)
    sl = find_swing_lows(df,  PIVOT_WINDOW)

    # Need at least 3 pivots of each type for a wedge
    min_pivots = 3
    # Scan windows of pivots
    for i in range(len(sh) - min_pivots + 1):
        h_pts = sh[i: i + min_pivots]
        # Match corresponding lows in same window
        l_pts = [j for j in sl if h_pts[0] <= j <= h_pts[-1]]
        if len(l_pts) < min_pivots:
            continue

        h_x = np.array(h_pts)
        h_y = df["high"].values[h_pts]
        l_x = np.array(l_pts[-min_pivots:])
        l_y = df["low"].values[l_pts[-min_pivots:]]

        h_slope, h_int, h_r = fit_trendline(h_x, h_y)
        l_slope, l_int, l_r = fit_trendline(l_x, l_y)

        # Both trendlines must slope the same direction
        if np.sign(h_slope) != np.sign(l_slope):
            continue
        # Upper line must slope less steeply than lower (converging)
        if abs(h_slope) >= abs(l_slope):
            continue
        if abs(h_r) < 0.7 or abs(l_r) < 0.7:
            continue

        start_idx = int(h_pts[0])
        end_idx   = int(h_pts[-1])
        price_at_end = df["close"].iloc[end_idx]
        pattern_range = float(h_y.max() - l_y.min())

        if pattern_range / price_at_end < MIN_PATTERN_DEPTH_PCT:
            continue

        if h_slope > 0:  # Rising Wedge → bearish
            neckline = float(l_int + l_slope * end_idx)  # lower trendline support
            trade = _trade_levels("bearish", neckline, neckline, pattern_range, df, end_idx)
            if trade["risk_reward"] < DEFAULT_RISK_REWARD:
                continue
            conf = 0.5 + 0.2 * (abs(h_r) > 0.85) + 0.2 * (abs(l_r) > 0.85) + 0.1 * (len(h_pts) > 3)
            results.append(_base_pattern(
                "Rising Wedge", "bearish", "reversal",
                start_idx, end_idx, df,
                {"upper_slope": round(h_slope,4), "lower_slope": round(l_slope,4),
                 "resistance": round(float(h_y[-1]),2), "support": round(float(l_y[-1]),2)},
                trade, conf, f"Upper slope={h_slope:.4f}, lower slope={l_slope:.4f}"
            ))
        else:  # Falling Wedge → bullish
            neckline = float(h_int + h_slope * end_idx)  # upper trendline resistance
            trade = _trade_levels("bullish", neckline, neckline, pattern_range, df, end_idx)
            if trade["risk_reward"] < DEFAULT_RISK_REWARD:
                continue
            conf = 0.5 + 0.2 * (abs(h_r) > 0.85) + 0.2 * (abs(l_r) > 0.85) + 0.1 * (len(h_pts) > 3)
            results.append(_base_pattern(
                "Falling Wedge", "bullish", "reversal",
                start_idx, end_idx, df,
                {"upper_slope": round(h_slope,4), "lower_slope": round(l_slope,4),
                 "resistance": round(float(h_y[-1]),2), "support": round(float(l_y[-1]),2)},
                trade, conf, f"Upper slope={h_slope:.4f}, lower slope={l_slope:.4f}"
            ))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# 9 & 10. BULL FLAG / BEAR FLAG
# ─────────────────────────────────────────────────────────────────────────────

def detect_flags(df: pd.DataFrame) -> PatternList:
    """
    Flagpole: sharp move (≥3% in ≤10 bars).
    Flag: counter-trend channel (≤50% retracement, ≤20 bars).
    Breakout: price closes beyond the flag in the trend direction.
    """
    results: PatternList = []
    closes = df["close"].values
    highs  = df["high"].values
    lows   = df["low"].values
    n = len(df)

    POLE_BARS  = 10
    POLE_PCT   = 0.02   # 2 % minimum pole move
    FLAG_BARS  = 20     # max consolidation bars
    RETRACE    = 0.55   # max retracement of pole

    for pole_start in range(0, n - POLE_BARS - FLAG_BARS):
        for pole_end in range(pole_start + 3, pole_start + POLE_BARS + 1):
            if pole_end >= n:
                break

            move = (closes[pole_end] - closes[pole_start]) / closes[pole_start]

            if move > POLE_PCT:   # Bull pole
                pole_high = highs[pole_start:pole_end + 1].max()
                pole_range = pole_high - closes[pole_start]

                # Flag consolidation
                flag_end = min(pole_end + FLAG_BARS, n - 1)
                flag_slice_h = highs[pole_end: flag_end + 1]
                flag_slice_l = lows[pole_end:  flag_end + 1]

                flag_high = flag_slice_h.max()
                flag_low  = flag_slice_l.min()

                # Must retrace ≤ RETRACE of pole
                if (pole_high - flag_low) / pole_range > RETRACE:
                    continue
                # Flag must slope slightly down
                if flag_slice_h.mean() > pole_high * 1.005:
                    continue

                trade = _trade_levels("bullish", flag_high, flag_high,
                                      pole_range, df, flag_end)
                if trade["risk_reward"] < DEFAULT_RISK_REWARD:
                    continue

                conf = 0.6 + 0.2 * (move > 0.04) + 0.1 * (pole_end - pole_start <= 5)
                results.append(_base_pattern(
                    "Bull Flag", "bullish", "continuation",
                    pole_start, flag_end, df,
                    {"pole_start": round(closes[pole_start],2),
                     "pole_high": round(pole_high,2),
                     "flag_low": round(flag_low,2),
                     "breakout": round(flag_high,2)},
                    trade, conf,
                    f"Pole move={move:.1%} in {pole_end-pole_start} bars"
                ))

            elif move < -POLE_PCT:  # Bear pole
                pole_low   = lows[pole_start:pole_end + 1].min()
                pole_range = closes[pole_start] - pole_low

                flag_end = min(pole_end + FLAG_BARS, n - 1)
                flag_slice_h = highs[pole_end: flag_end + 1]
                flag_slice_l = lows[pole_end:  flag_end + 1]

                flag_high = flag_slice_h.max()
                flag_low  = flag_slice_l.min()

                if (flag_high - pole_low) / pole_range > RETRACE:
                    continue
                if flag_slice_l.mean() < pole_low * 0.995:
                    continue

                trade = _trade_levels("bearish", flag_low, flag_low,
                                      pole_range, df, flag_end)
                if trade["risk_reward"] < DEFAULT_RISK_REWARD:
                    continue

                conf = 0.6 + 0.2 * (abs(move) > 0.04) + 0.1 * (pole_end - pole_start <= 5)
                results.append(_base_pattern(
                    "Bear Flag", "bearish", "continuation",
                    pole_start, flag_end, df,
                    {"pole_start": round(closes[pole_start],2),
                     "pole_low": round(pole_low,2),
                     "flag_high": round(flag_high,2),
                     "breakdown": round(flag_low,2)},
                    trade, conf,
                    f"Pole move={move:.1%} in {pole_end-pole_start} bars"
                ))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# 11 & 12. BULL PENNANT / BEAR PENNANT
# ─────────────────────────────────────────────────────────────────────────────

def detect_pennants(df: pd.DataFrame) -> PatternList:
    """
    Like flags but consolidation is a symmetrical triangle (converging H/L).
    """
    results: PatternList = []
    closes = df["close"].values
    highs  = df["high"].values
    lows   = df["low"].values
    n = len(df)

    POLE_BARS = 10
    POLE_PCT  = 0.02
    PNNT_BARS = 15

    for pole_start in range(0, n - POLE_BARS - PNNT_BARS):
        for pole_end in range(pole_start + 3, min(pole_start + POLE_BARS + 1, n)):
            move = (closes[pole_end] - closes[pole_start]) / closes[pole_start]
            if abs(move) < POLE_PCT:
                continue

            pnnt_end = min(pole_end + PNNT_BARS, n - 1)
            ph = highs[pole_end: pnnt_end + 1]
            pl = lows[pole_end:  pnnt_end + 1]

            if len(ph) < 4:
                continue

            x  = np.arange(len(ph))
            h_slope, h_int, h_r = fit_trendline(x, ph)
            l_slope, l_int, l_r = fit_trendline(x, pl)

            # Converging: upper declining, lower rising
            if not (h_slope < 0 < l_slope):
                continue
            if abs(h_r) < 0.6 or abs(l_r) < 0.6:
                continue

            pole_range = abs(closes[pole_end] - closes[pole_start])
            breakout_price = float(h_int + h_slope * len(ph)) if move > 0 else float(l_int + l_slope * len(pl))

            direction = "bullish" if move > 0 else "bearish"
            trade = _trade_levels(direction, breakout_price, breakout_price, pole_range, df, pnnt_end)
            if trade["risk_reward"] < DEFAULT_RISK_REWARD:
                continue

            name = "Bull Pennant" if move > 0 else "Bear Pennant"
            conf = 0.55 + 0.2 * (abs(h_r) > 0.8) + 0.2 * (abs(l_r) > 0.8)
            results.append(_base_pattern(
                name, direction, "continuation",
                pole_start, pnnt_end, df,
                {"pole_move": round(move * 100, 2),
                 "pennant_high": round(float(ph.max()),2),
                 "pennant_low": round(float(pl.min()),2)},
                trade, conf,
                f"Pole={move:.1%}, upper slope={h_slope:.4f}, lower slope={l_slope:.4f}"
            ))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# 13 & 14 & 15. TRIANGLES (Ascending / Descending / Symmetrical)
# ─────────────────────────────────────────────────────────────────────────────

def detect_triangles(df: pd.DataFrame) -> PatternList:
    results: PatternList = []
    sh = find_swing_highs(df, PIVOT_WINDOW)
    sl = find_swing_lows(df,  PIVOT_WINDOW)
    WINDOW = 5  # look at last N pivots each side

    for i in range(len(sh) - WINDOW + 1):
        h_pts = sh[i: i + WINDOW]
        l_pts = [j for j in sl if h_pts[0] <= j <= h_pts[-1]]
        if len(l_pts) < WINDOW:
            continue

        l_pts = l_pts[-WINDOW:]
        h_x = np.array(h_pts);   h_y = df["high"].values[h_pts]
        l_x = np.array(l_pts);   l_y = df["low"].values[l_pts]

        h_slope, h_int, h_r = fit_trendline(h_x.astype(float), h_y)
        l_slope, l_int, l_r = fit_trendline(l_x.astype(float), l_y)

        if abs(h_r) < 0.65 or abs(l_r) < 0.65:
            continue

        start_idx = int(h_pts[0])
        end_idx   = int(h_pts[-1])
        price_end = df["close"].iloc[end_idx]
        pattern_h = float(h_y.max() - l_y.min())

        if pattern_h / price_end < MIN_PATTERN_DEPTH_PCT:
            continue

        resist_at_end = h_int + h_slope * end_idx
        support_at_end = l_int + l_slope * end_idx

        flat_thresh = 0.00005  # slope per bar considered "flat"

        h_flat = abs(h_slope / price_end) < flat_thresh
        l_flat = abs(l_slope / price_end) < flat_thresh

        if h_flat and not l_flat and l_slope > 0:
            # Ascending Triangle → bullish
            trade = _trade_levels("bullish", resist_at_end, resist_at_end,
                                  pattern_h, df, end_idx)
            if trade["risk_reward"] < DEFAULT_RISK_REWARD:
                continue
            conf = 0.55 + 0.2 * (abs(l_r) > 0.85) + 0.15 * (WINDOW >= 4)
            results.append(_base_pattern(
                "Ascending Triangle", "bullish", "continuation",
                start_idx, end_idx, df,
                {"resistance": round(resist_at_end,2), "support_slope": round(l_slope,4)},
                trade, conf, f"Flat top at {resist_at_end:.0f}, rising lows"
            ))

        elif l_flat and not h_flat and h_slope < 0:
            # Descending Triangle → bearish
            trade = _trade_levels("bearish", support_at_end, support_at_end,
                                  pattern_h, df, end_idx)
            if trade["risk_reward"] < DEFAULT_RISK_REWARD:
                continue
            conf = 0.55 + 0.2 * (abs(h_r) > 0.85) + 0.15 * (WINDOW >= 4)
            results.append(_base_pattern(
                "Descending Triangle", "bearish", "continuation",
                start_idx, end_idx, df,
                {"support": round(support_at_end,2), "resistance_slope": round(h_slope,4)},
                trade, conf, f"Flat bottom at {support_at_end:.0f}, falling highs"
            ))

        elif not h_flat and not l_flat and h_slope < 0 and l_slope > 0:
            # Symmetrical Triangle → bias from prior trend
            prior_close = df["close"].iloc[max(0, start_idx - 20)]
            entry_close = df["close"].iloc[start_idx]
            prior_trend = "bullish" if entry_close > prior_close else "bearish"
            breakout_level = resist_at_end if prior_trend == "bullish" else support_at_end
            trade = _trade_levels(prior_trend, breakout_level, breakout_level,
                                  pattern_h, df, end_idx)
            if trade["risk_reward"] < DEFAULT_RISK_REWARD:
                continue
            conf = 0.45 + 0.2 * (abs(h_r) > 0.8) + 0.2 * (abs(l_r) > 0.8)
            results.append(_base_pattern(
                "Symmetrical Triangle", prior_trend, "continuation",
                start_idx, end_idx, df,
                {"resistance": round(resist_at_end,2), "support": round(support_at_end,2)},
                trade, conf, f"Upper slope={h_slope:.4f}, lower slope={l_slope:.4f}"
            ))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# 16 & 17. ASCENDING / DESCENDING CHANNEL
# ─────────────────────────────────────────────────────────────────────────────

def detect_channels(df: pd.DataFrame) -> PatternList:
    results: PatternList = []
    sh = find_swing_highs(df, PIVOT_WINDOW)
    sl = find_swing_lows(df,  PIVOT_WINDOW)
    WINDOW = 4

    for i in range(len(sh) - WINDOW + 1):
        h_pts = sh[i: i + WINDOW]
        l_pts = [j for j in sl if h_pts[0] <= j <= h_pts[-1]]
        if len(l_pts) < WINDOW:
            continue

        l_pts = l_pts[-WINDOW:]
        h_x = np.array(h_pts,  dtype=float); h_y = df["high"].values[h_pts]
        l_x = np.array(l_pts,  dtype=float); l_y = df["low"].values[l_pts]

        h_slope, h_int, h_r = fit_trendline(h_x, h_y)
        l_slope, l_int, l_r = fit_trendline(l_x, l_y)

        if abs(h_r) < 0.75 or abs(l_r) < 0.75:
            continue

        # Parallel: slopes must be close to each other
        if abs(h_slope - l_slope) / (abs(h_slope) + 1e-9) > 0.5:
            continue

        price_end = df["close"].iloc[int(h_pts[-1])]
        channel_h = float(h_y[-1] - l_y[-1])
        if channel_h / price_end < MIN_PATTERN_DEPTH_PCT:
            continue

        start_idx = int(h_pts[0])
        end_idx   = int(h_pts[-1])
        resist = float(h_int + h_slope * end_idx)
        support = float(l_int + l_slope * end_idx)

        if h_slope > 0 and l_slope > 0:  # Ascending Channel
            trade = _trade_levels("bullish", support, support, channel_h, df, end_idx)
            if trade["risk_reward"] < DEFAULT_RISK_REWARD:
                continue
            conf = 0.5 + 0.2 * (abs(h_r) > 0.9) + 0.2 * (abs(l_r) > 0.9)
            results.append(_base_pattern(
                "Ascending Channel", "bullish", "continuation",
                start_idx, end_idx, df,
                {"upper_channel": round(resist,2), "lower_channel": round(support,2)},
                trade, conf, f"Buy at support {support:.0f}, target {resist:.0f}"
            ))
        elif h_slope < 0 and l_slope < 0:  # Descending Channel
            trade = _trade_levels("bearish", resist, resist, channel_h, df, end_idx)
            if trade["risk_reward"] < DEFAULT_RISK_REWARD:
                continue
            conf = 0.5 + 0.2 * (abs(h_r) > 0.9) + 0.2 * (abs(l_r) > 0.9)
            results.append(_base_pattern(
                "Descending Channel", "bearish", "continuation",
                start_idx, end_idx, df,
                {"upper_channel": round(resist,2), "lower_channel": round(support,2)},
                trade, conf, f"Sell at resistance {resist:.0f}, target {support:.0f}"
            ))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# 18. CUP AND HANDLE
# ─────────────────────────────────────────────────────────────────────────────

def detect_cup_and_handle(df: pd.DataFrame) -> PatternList:
    """
    Cup: U-shaped pullback (30-65 bars), both lips roughly equal.
    Handle: Small pullback after right lip (10-20 bars, ≤50% of cup depth).
    Breakout: Above right lip (cup rim).
    """
    results: PatternList = []
    sh = find_swing_highs(df, PIVOT_WINDOW)
    sl = find_swing_lows(df,  PIVOT_WINDOW)
    n  = len(df)

    CUP_MIN, CUP_MAX   = 20, 100   # bars
    HANDLE_MIN, HANDLE_MAX = 5, 30

    for i in range(len(sh) - 1):
        left_lip_idx = sh[i]
        left_lip     = df["high"].iloc[left_lip_idx]

        # Find cup bottom (lowest low between this high and next high)
        for j in range(i + 1, len(sh)):
            right_lip_idx = sh[j]
            right_lip     = df["high"].iloc[right_lip_idx]

            cup_bars = right_lip_idx - left_lip_idx
            if cup_bars < CUP_MIN or cup_bars > CUP_MAX:
                if cup_bars > CUP_MAX:
                    break
                continue

            if not prices_approx_equal(left_lip, right_lip, PRICE_TOLERANCE_PCT * 3):
                continue

            cup_lows = [k for k in sl if left_lip_idx < k < right_lip_idx]
            if not cup_lows:
                continue
            cup_bottom_idx = min(cup_lows, key=lambda k: df["low"].iloc[k])
            cup_bottom = df["low"].iloc[cup_bottom_idx]
            cup_depth  = (left_lip + right_lip) / 2 - cup_bottom

            # Cup must have meaningful depth
            if cup_depth / left_lip < 0.02:
                continue

            # ── Handle ───────────────────────────────────────────────────────
            handle_slice = df.iloc[right_lip_idx: min(right_lip_idx + HANDLE_MAX + 1, n)]
            if len(handle_slice) < HANDLE_MIN:
                continue

            handle_low  = handle_slice["low"].min()
            handle_retr = (right_lip - handle_low) / cup_depth
            if handle_retr > 0.5 or handle_retr < 0.05:
                continue

            # Breakout at right lip
            rim = right_lip
            trade = _trade_levels("bullish", rim, rim, cup_depth, df,
                                  min(right_lip_idx + HANDLE_MAX, n - 1))
            if trade["risk_reward"] < DEFAULT_RISK_REWARD:
                continue

            conf = 0.55 + 0.2 * (prices_approx_equal(left_lip, right_lip, PRICE_TOLERANCE_PCT)) + \
                   0.15 * (cup_depth / left_lip > 0.05) + 0.1 * (handle_retr < 0.3)

            results.append(_base_pattern(
                "Cup and Handle", "bullish", "continuation",
                left_lip_idx, right_lip_idx, df,
                {"left_lip": round(left_lip,2), "cup_bottom": round(cup_bottom,2),
                 "right_lip": round(right_lip,2), "rim": round(rim,2)},
                trade, conf,
                f"Cup depth={cup_depth:.0f} ({cup_depth/left_lip:.1%}), handle retr={handle_retr:.0%}"
            ))
            break  # one cup per left lip

    return results


# ─────────────────────────────────────────────────────────────────────────────
# MASTER RUNNER
# ─────────────────────────────────────────────────────────────────────────────

ALL_DETECTORS = [
    ("Head & Shoulders / Inverse",      detect_head_and_shoulders),
    ("Double Top / Double Bottom",       detect_double_top_bottom),
    ("Triple Top / Triple Bottom",       detect_triple_top_bottom),
    ("Rising / Falling Wedge",           detect_wedges),
    ("Bull Flag / Bear Flag",            detect_flags),
    ("Bull Pennant / Bear Pennant",      detect_pennants),
    ("Triangles",                        detect_triangles),
    ("Channels",                         detect_channels),
    ("Cup and Handle",                   detect_cup_and_handle),
]


def _session_frames(df: pd.DataFrame):
    """Yield (local frame, position map) for each trading day.

    Detectors see one session at a time, so swing points cannot connect
    the close of one day to the open of the next.
    """
    ts = pd.DatetimeIndex(df.index)
    if ts.tz is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    day_keys = ts.normalize()
    min_bars = PIVOT_WINDOW * 2 + 5

    for day in pd.unique(day_keys):
        positions = np.flatnonzero(day_keys == day)
        if len(positions) < min_bars:
            continue
        if positions[-1] - positions[0] + 1 == len(positions):
            local = df.iloc[int(positions[0]): int(positions[-1]) + 1]
            index_map = None
            offset = int(positions[0])
        else:
            local = df.iloc[positions]
            index_map = positions
            offset = 0
        yield local, index_map, offset


def detect_all_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Run every detector inside each trading session and return a
    deduplicated, sorted DataFrame of intraday patterns.
    """
    all_patterns: PatternList = []
    counts = {name: 0 for name, _ in ALL_DETECTORS}
    n_sessions = 0

    for local, index_map, offset in _session_frames(df):
        n_sessions += 1
        for name, detector in ALL_DETECTORS:
            try:
                found = detector(local)
            except Exception as exc:
                print(f"  [{name}]: ERROR – {exc}")
                continue
            for pattern in found:
                if index_map is None:
                    pattern["start_idx"] = offset + int(pattern["start_idx"])
                    pattern["end_idx"] = offset + int(pattern["end_idx"])
                else:
                    pattern["start_idx"] = int(index_map[int(pattern["start_idx"])])
                    pattern["end_idx"] = int(index_map[int(pattern["end_idx"])])
            counts[name] += len(found)
            all_patterns.extend(found)

    print(f"  [sessions]: {n_sessions} trading day(s), intraday only")
    for name, n in counts.items():
        print(f"  [{name}]: {n} pattern(s) found")

    if not all_patterns:
        return pd.DataFrame()

    result = pd.DataFrame(all_patterns)
    start_day = pd.to_datetime(result["start_date"], utc=True).dt.tz_localize(None).dt.normalize()
    end_day = pd.to_datetime(result["end_date"], utc=True).dt.tz_localize(None).dt.normalize()
    result = result.loc[start_day.values == end_day.values].copy()
    result = result.sort_values("end_date", ascending=False).reset_index(drop=True)

    # Remove near-duplicate patterns (same pattern, close start/end)
    result["_key"] = result["pattern"] + "_" + result["start_idx"].astype(str)
    result = result.drop_duplicates(subset="_key").drop(columns="_key")

    return result
