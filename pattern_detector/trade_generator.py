"""
Trade File Generator
====================
Takes detected patterns and outputs a structured CSV trade file with:
  - Trade ID, Symbol, Pattern, Direction, Type
  - Entry, Stop Loss, Target 1 (1R), Target 2 (2R), Target 3 (3R)
  - Risk/Reward, Position Size, Risk ₹, Max Profit ₹
  - Pattern Dates, Confidence, Notes
"""
from __future__ import annotations

import pandas as pd
import numpy as np
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from pattern_detector.config import (
    SYMBOL, CAPITAL, DEFAULT_RISK_PCT, OUTPUT_DIR, TRADE_FILE
)


def _calc_position_size(entry: float, stop: float) -> dict:
    """
    Calculate position size based on fixed risk % of capital.
    Risk ₹ = CAPITAL × DEFAULT_RISK_PCT
    Qty    = Risk ₹ / (entry - stop)
    """
    risk_per_trade = CAPITAL * DEFAULT_RISK_PCT
    risk_per_unit  = abs(entry - stop)

    if risk_per_unit <= 0:
        qty = 0
    else:
        qty = int(risk_per_trade / risk_per_unit)

    risk_amt    = round(qty * risk_per_unit, 2)
    return {
        "qty"          : qty,
        "risk_amt_inr" : risk_amt,
        "risk_pct"     : round(risk_amt / CAPITAL * 100, 3),
    }


def build_trade_file(patterns_df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate a structured trade CSV from pattern detections.
    Returns the trades DataFrame and saves it to TRADE_FILE.
    """
    if patterns_df.empty:
        print("[trade_gen] No patterns found, no trade file generated.")
        return pd.DataFrame()

    trades = []
    for tid, row in enumerate(patterns_df.itertuples(), start=1):
        entry    = getattr(row, "entry",     None)
        sl       = getattr(row, "stop_loss", None)
        target1  = getattr(row, "target",    None)  # 1R target from detector

        if entry is None or sl is None or target1 is None:
            continue
        if entry <= 0 or sl <= 0:
            continue

        risk_per_unit = abs(entry - sl)
        direction     = getattr(row, "direction", "bullish")

        # Compute T1 (1R), T2 (2R), T3 (3R)
        sign = 1 if direction == "bullish" else -1
        t1 = round(entry + sign * risk_per_unit * 1.5, 2)
        t2 = round(entry + sign * risk_per_unit * 2.5, 2)
        t3 = round(entry + sign * risk_per_unit * 4.0, 2)

        pos = _calc_position_size(entry, sl)

        # Key levels from the pattern
        kl = getattr(row, "key_levels", {})
        kl_str = " | ".join(f"{k}={v}" for k, v in kl.items())

        trade = {
            "trade_id"         : f"T{tid:04d}",
            "symbol"           : SYMBOL,
            "pattern"          : getattr(row, "pattern",    "—"),
            "direction"        : direction.upper(),
            "type"             : getattr(row, "type",       "—"),
            "pattern_start"    : str(getattr(row, "start_date", ""))[:19],
            "pattern_end"      : str(getattr(row, "end_date",   ""))[:19],
            "entry_price"      : round(entry,  2),
            "stop_loss"        : round(sl,     2),
            "target_1R"        : t1,
            "target_2R"        : t2,
            "target_3R"        : t3,
            "risk_reward"      : getattr(row, "risk_reward", 0),
            "position_size"    : pos["qty"],
            "risk_inr"         : pos["risk_amt_inr"],
            "risk_pct"         : pos["risk_pct"],
            "max_profit_1R_inr": round(pos["qty"] * abs(t1 - entry), 2),
            "max_profit_2R_inr": round(pos["qty"] * abs(t2 - entry), 2),
            "max_profit_3R_inr": round(pos["qty"] * abs(t3 - entry), 2),
            "confidence"       : getattr(row, "confidence",  0),
            "key_levels"       : kl_str,
            "notes"            : getattr(row, "notes",       ""),
            "status"           : "PENDING",
        }
        trades.append(trade)

    if not trades:
        print("[trade_gen] No valid trades generated.")
        return pd.DataFrame()

    df_trades = pd.DataFrame(trades)

    # Sort: highest confidence first
    df_trades = df_trades.sort_values(
        ["confidence", "risk_reward"], ascending=[False, False]
    ).reset_index(drop=True)

    # Re-number trade IDs
    df_trades["trade_id"] = [f"T{i+1:04d}" for i in range(len(df_trades))]

    # Save CSV
    df_trades.to_csv(TRADE_FILE, index=False)
    print(f"[trade_gen] ✅  {len(df_trades)} trade(s) written → {TRADE_FILE}")

    return df_trades
