"""
Main Entry Point
================
Run the full pipeline:
  1. Fetch OHLCV from QuestDB
  2. Detect all chart patterns
  3. Generate trade file (CSV)
  4. Generate candlestick charts (PNG)
  5. Build HTML report

Usage:
    python run.py
    python run.py --resample 1H --days 180
"""
from __future__ import annotations

import argparse, sys, os, time
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(__file__))

from pattern_detector.data_loader    import load_ohlcv
from pattern_detector.patterns       import detect_all_patterns
from pattern_detector.trade_generator import build_trade_file
from pattern_detector.chart_generator import generate_all_charts
from pattern_detector.report_generator import generate_report
from pattern_detector.config import TRADE_FILE, REPORT_FILE, SYMBOL


def main():
    parser = argparse.ArgumentParser(description="Chart Pattern Detector for NIFTY 50")
    parser.add_argument("--resample", default=None,
                        help="Override resample timeframe: 5min, 15min, 30min, 1H, 1D")
    parser.add_argument("--days",     type=int, default=None,
                        help="Override lookback days (default: from config)")
    parser.add_argument("--no-charts", action="store_true",
                        help="Skip chart generation (faster)")
    parser.add_argument("--max-charts", type=int, default=30,
                        help="Max number of charts to generate")
    args = parser.parse_args()

    print("=" * 65)
    print(f"  Chart Pattern Detection System — {SYMBOL}")
    print("=" * 65)

    t0 = time.time()

    # ── 1. Load Data ──────────────────────────────────────────────────────────
    print("\n[1/5] Loading OHLCV data from QuestDB …")
    kw = {}
    if args.resample: kw["resample_to"] = args.resample
    if args.days:     kw["lookback_days"] = args.days
    df = load_ohlcv(**kw)
    print(f"      Loaded {len(df):,} bars | {df.index[0]} → {df.index[-1]}")

    # ── 2. Detect Patterns ────────────────────────────────────────────────────
    print("\n[2/5] Running pattern detection …")
    patterns_df = detect_all_patterns(df)
    print(f"      Total patterns detected: {len(patterns_df)}")

    if patterns_df.empty:
        print("\n⚠️  No patterns detected. Try adjusting PIVOT_WINDOW or tolerances in config.py")
        print("     Generating empty report …")
        import pandas as pd
        build_trade_file(pd.DataFrame())
        generate_report(pd.DataFrame(), pd.DataFrame(), {}, df)
        return

    # ── 3. Build Trade File ───────────────────────────────────────────────────
    print("\n[3/5] Building trade file …")
    trades_df = build_trade_file(patterns_df)

    # Add trade_id to patterns_df for chart mapping
    patterns_df = patterns_df.head(len(trades_df)).copy()
    if len(trades_df):
        patterns_df["trade_id"] = trades_df["trade_id"].values[:len(patterns_df)]

    # ── 4. Generate Charts ────────────────────────────────────────────────────
    charts = {}
    # Merge trade_id back into patterns for chart generation (patterns has start_idx)
    chart_df = patterns_df.copy()
    if len(trades_df) and "trade_id" in trades_df.columns:
        chart_df["trade_id"] = trades_df["trade_id"].values[:len(chart_df)]
    # Also propagate entry/stop/target from trades_df into chart_df
    for col in ["entry_price", "stop_loss", "target_1R", "risk_reward", "confidence"]:
        if col in trades_df.columns and col not in chart_df.columns:
            chart_df[col] = trades_df[col].values[:len(chart_df)]
    # Rename entry_price -> entry if needed
    if "entry_price" in chart_df.columns and "entry" not in chart_df.columns:
        chart_df["entry"] = chart_df["entry_price"]
    if "target_1R" in chart_df.columns and "target" not in chart_df.columns:
        chart_df["target"] = chart_df["target_1R"]

    if not args.no_charts:
        print(f"\n[4/5] Generating charts (max {args.max_charts}) ...")
        charts = generate_all_charts(df, chart_df, max_charts=args.max_charts)
    else:
        print("\n[4/5] Chart generation skipped (--no-charts)")

    # ── 5. HTML Report ────────────────────────────────────────────────────────
    print("\n[5/5] Generating HTML report …")
    report_path = generate_report(patterns_df, trades_df, charts, df)

    # ── Summary ───────────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    print("\n" + "=" * 65)
    print(f"  ✅  Pipeline complete in {elapsed:.1f}s")
    print(f"  📊  Patterns  : {len(patterns_df)}")
    print(f"  📁  Trade CSV : {TRADE_FILE}")
    print(f"  🌐  Report    : {REPORT_FILE}")
    print("=" * 65)


if __name__ == "__main__":
    main()
