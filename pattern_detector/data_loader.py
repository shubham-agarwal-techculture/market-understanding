"""
QuestDB Data Loader
Fetches OHLC data via QuestDB REST API and resamples to target timeframe.
"""
from __future__ import annotations

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from pattern_detector.config import (
    QUESTDB_HOST, QUESTDB_TABLE, LOOKBACK_DAYS, RESAMPLE_TO
)


def _run_query(sql: str) -> pd.DataFrame:
    """Execute SQL on QuestDB REST API and return a DataFrame."""
    url = f"{QUESTDB_HOST}/exec"
    params = {"query": sql, "count": "true"}
    resp = requests.get(url, params=params, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        raise RuntimeError(f"QuestDB error: {data['error']}")

    columns = [col["name"] for col in data["columns"]]
    rows = data.get("dataset", [])
    return pd.DataFrame(rows, columns=columns)


def load_ohlcv(
    lookback_days: int = LOOKBACK_DAYS,
    resample_to: str = RESAMPLE_TO,
) -> pd.DataFrame:
    """
    Fetch 1-min OHLCV from QuestDB and resample to `resample_to` frequency.
    
    Returns a DataFrame with columns:
        open, high, low, close, volume
    indexed by a UTC-aware DatetimeIndex named 'date'.
    """
    end_dt   = datetime.utcnow()
    start_dt = end_dt - timedelta(days=lookback_days)

    start_str = start_dt.strftime("%Y-%m-%dT%H:%M:%S")
    end_str   = end_dt.strftime("%Y-%m-%dT%H:%M:%S")

    sql = (
        f"SELECT date, open, high, low, close, volume "
        f"FROM {QUESTDB_TABLE} "
        f"WHERE date >= '{start_str}' AND date <= '{end_str}' "
        f"ORDER BY date ASC"
    )

    print(f"[loader] Fetching data from {start_str} -> {end_str} ...")
    df = _run_query(sql)

    if df.empty:
        raise ValueError("No data returned from QuestDB. Check date range and table name.")

    # ── Parse timestamps ───────────────────────────────────────────────────────
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df.set_index("date").sort_index()

    # ── Cast numeric columns ───────────────────────────────────────────────────
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)

    df = df.dropna(subset=["open", "high", "low", "close"])

    raw_count = len(df)
    print(f"[loader] Raw 1-min bars loaded: {raw_count:,}")

    # ── Resample ───────────────────────────────────────────────────────────────
    if resample_to and resample_to != "1min":
        # Map friendly string → pandas offset alias
        freq_map = {
            "5min": "5min", "15min": "15min", "30min": "30min",
            "1H": "1h", "1D": "1D",
        }
        freq = freq_map.get(resample_to, resample_to)

        df = df.resample(freq).agg(
            open=("open",   "first"),
            high=("high",   "max"),
            low=("low",     "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        ).dropna(subset=["open"])

        print(f"[loader] Resampled to {resample_to}: {len(df):,} bars")

    return df


def get_daily_df(lookback_days: int = LOOKBACK_DAYS) -> pd.DataFrame:
    """Return Daily OHLCV bars (1-min data aggregated to daily)."""
    return load_ohlcv(lookback_days=lookback_days, resample_to="1D")


if __name__ == "__main__":
    df = load_ohlcv()
    print(df.tail())
    print(df.dtypes)
