# 📊 Chart Pattern Detection System — NIFTY 50

> Automated technical analysis pipeline that fetches live OHLCV data from **QuestDB**, detects **18 chart patterns** based on the [TheChartGuys Pattern Framework](https://www.chartguys.com), generates **trade setups** with full risk management, produces **annotated candlestick charts**, and compiles everything into a **dark-themed interactive HTML report**.

---

## 🗂️ Table of Contents

1. [Overview](#-overview)
2. [System Architecture](#-system-architecture)
3. [Project Structure](#-project-structure)
4. [Detected Patterns](#-detected-patterns)
5. [How Pattern Detection Works](#-how-pattern-detection-works)
6. [Trade Setup Logic](#-trade-setup-logic)
7. [Risk Management](#-risk-management)
8. [Output Files](#-output-files)
9. [Configuration Reference](#-configuration-reference)
10. [Installation & Setup](#-installation--setup)
11. [Running the Pipeline](#-running-the-pipeline)
12. [CLI Arguments](#-cli-arguments)
13. [Module Reference](#-module-reference)
14. [Sample Results](#-sample-results-last-1-year)
15. [Extending the System](#-extending-the-system)
16. [Troubleshooting](#-troubleshooting)

---

## 🔭 Overview

This system is designed for **systematic technical analysis** of Indian equity indices, specifically **NSE NIFTY 50**. It automates the entire workflow a human chartist would follow:

```
QuestDB (Live OHLCV)
       |
       v
  Resample to 15-min bars
       |
       v
  Detect 18 Chart Patterns (swing pivots + trendline fitting)
       |
       v
  Calculate Entry / Stop-Loss / Target levels per pattern
       |
       v
  Size positions using fixed-risk % of capital
       |
       v
  Generate annotated PNG charts (1 per trade)
       |
       v
  Build interactive HTML report + CSV trade file
```

**Key design principles:**
- **No manual intervention** — fully automated from raw OHLCV to trade file
- **All patterns from TheChartGuys cheat sheet** — reversal and continuation
- **Risk-first sizing** — every trade risks exactly 1% of capital by default
- **Minimum R:R filter** — patterns with < 2x risk:reward are discarded
- **Volume confirmation** — breakout bar volume must spike vs. 20-period average

---

## 🏗️ System Architecture

```
+--------------------------------------------------------------------+
|                        run.py  (Orchestrator)                       |
+--------------------------------------------------------------------+
          |           |            |            |            |
          v           v            v            v            v
   data_loader   patterns.py  trade_generator chart_generator report_generator
       .py            |            .py             .py            .py
          |           |
          v           v
      QuestDB     utils.py
    REST API    (swing points,
  /exec endpoint  trendlines,
                  ATR, volume)
```

### Data Flow

| Step | Module | Input | Output |
|------|--------|-------|--------|
| 1 | `data_loader.py` | QuestDB table `nse_nifty_50` | Resampled OHLCV DataFrame |
| 2 | `patterns.py` | OHLCV DataFrame | List of pattern dicts |
| 3 | `trade_generator.py` | Pattern list | `trades.csv` |
| 4 | `chart_generator.py` | OHLCV + patterns | PNG chart files |
| 5 | `report_generator.py` | Patterns + trades + charts | `report.html` |

---

## 📁 Project Structure

```
market_understanding/
|
+-- run.py                          # Main entry point -- runs full pipeline
|
+-- pattern_detector/               # Core package
|   +-- __init__.py
|   +-- config.py                   # All tunable parameters
|   +-- data_loader.py              # QuestDB REST API + resampling
|   +-- utils.py                    # Shared helpers (swings, ATR, trendlines)
|   +-- patterns.py                 # 18 pattern detector functions
|   +-- trade_generator.py          # Trade file builder with position sizing
|   +-- chart_generator.py          # Dark-themed candlestick chart renderer
|   +-- report_generator.py         # Self-contained HTML report generator
|
+-- pattern_detector/output/        # Generated outputs (auto-created)
    +-- trades.csv                  # Trade setups (CSV)
    +-- report.html                 # Interactive HTML report
    +-- charts/                     # Per-pattern PNG charts
        +-- T0001_Triple_Top.png
        +-- T0002_Rising_Wedge.png
        +-- ... (up to max_charts)
```

---

## 📐 Detected Patterns

The system implements all patterns from **TheChartGuys Chart Pattern Cheat Sheet**, split into two categories:

### 🔄 Reversal Patterns
These form at the end of a trend and signal a direction change.

| # | Pattern | Signal | Trigger |
|---|---------|--------|---------|
| 1 | **Head & Shoulders** | Bearish | Close below neckline |
| 2 | **Inverse Head & Shoulders** | Bullish | Close above neckline |
| 3 | **Double Top** | Bearish | Close below valley (neckline) |
| 4 | **Double Bottom** | Bullish | Close above peak (neckline) |
| 5 | **Triple Top** | Bearish | Close below support |
| 6 | **Triple Bottom** | Bullish | Close above resistance |
| 7 | **Rising Wedge** | Bearish | Break below lower trendline |
| 8 | **Falling Wedge** | Bullish | Break above upper trendline |

### Continuation Patterns
These form during a trend pause and signal resumption.

| # | Pattern | Signal | Trigger |
|---|---------|--------|---------|
| 9 | **Bull Flag** | Bullish | Break above flag upper boundary |
| 10 | **Bear Flag** | Bearish | Break below flag lower boundary |
| 11 | **Bull Pennant** | Bullish | Break above converging upper line |
| 12 | **Bear Pennant** | Bearish | Break below converging lower line |
| 13 | **Ascending Triangle** | Bullish | Close above flat resistance |
| 14 | **Descending Triangle** | Bearish | Close below flat support |
| 15 | **Symmetrical Triangle** | Trend-bias | Break in direction of prior trend |
| 16 | **Ascending Channel** | Bullish | Buy at lower channel support |
| 17 | **Descending Channel** | Bearish | Sell at upper channel resistance |
| 18 | **Cup and Handle** | Bullish | Close above cup rim (right lip) |

---

## 🔍 How Pattern Detection Works

### Step 1 — Swing Pivot Detection

All pattern detectors start by identifying **swing highs** and **swing lows** using `scipy.signal.argrelextrema`:

```python
# A swing high: higher than the N bars on each side
find_swing_highs(df, window=PIVOT_WINDOW)   # default window = 5

# A swing low: lower than the N bars on each side
find_swing_lows(df, window=PIVOT_WINDOW)
```

> **Tip:** Increasing `PIVOT_WINDOW` in `config.py` finds larger, more significant swings and reduces noise patterns.

### Step 2 — Pattern Geometry Checks

Each detector applies **structural rules** specific to the pattern:

| Rule | Example |
|------|---------|
| Price level equality | Both Double Top peaks within `0.3%` of each other |
| Slope direction | Rising Wedge: both trendlines slope up, upper less steep than lower |
| Depth threshold | Pattern height must be >= `0.4%` of price to filter noise |
| Bar spacing | Double Top peaks must be >= `2 x PIVOT_WINDOW` bars apart |
| Trendline R-squared | Wedges/Triangles require `R >= 0.7` for fit quality |

### Step 3 — Trendline Fitting

For patterns requiring trendlines (wedges, triangles, channels, pennants), **linear regression** is used via `scipy.stats.linregress`:

```python
slope, intercept, r_value = linregress(x_indices, prices)
```

The `r_value` (correlation) gates pattern acceptance — poor fits are rejected.

### Step 4 — Volume Confirmation

If `VOLUME_CONFIRM = True`, the breakout bar's volume must be >= `VOLUME_MULT x 20-bar average`:

```python
volume_spike(df, breakout_idx, period=20, mult=1.3)
```

### Step 5 — Confidence Score

Each detected pattern receives a `confidence` score (0–1) composed of:

| Component | Contribution |
|-----------|-------------|
| Base score | `0.45 – 0.60` (varies by pattern reliability) |
| Volume spike confirmed | `+0.20` |
| Pattern depth > 2% | `+0.15` |
| Tight price level match | `+0.15` |
| High trendline R-squared | `+0.20` |

---

## 💹 Trade Setup Logic

Each confirmed pattern generates a **trade setup** with the following levels:

### Entry

```
Bullish:  Entry = Neckline / Resistance + (price x 0.2%)  # buy on breakout
Bearish:  Entry = Neckline / Support    - (price x 0.2%)  # sell on breakdown
```

### Stop Loss

```
Bullish:  Stop = Entry - max(buffer x 3, ATR x 0.5)
Bearish:  Stop = Entry + max(buffer x 3, ATR x 0.5)
```

Stop is placed beyond the pattern's extreme with an ATR-based floor so it's never too tight.

### Targets (Multi-level)

| Target | Formula | Purpose |
|--------|---------|---------|
| **T1 (1.5R)** | `Entry +/- (risk x 1.5)` | Conservative exit, partial profits |
| **T2 (2.5R)** | `Entry +/- (risk x 2.5)` | Core position exit |
| **T3 (4.0R)** | `Entry +/- (risk x 4.0)` | Runner / trailing stop |

> Patterns that don't meet the minimum **2x R:R** requirement are **discarded** from the trade file.

---

## 🛡️ Risk Management

### Position Sizing (Fixed Fractional)

Every trade risks exactly `DEFAULT_RISK_PCT` (default: **1%**) of `CAPITAL`:

```
Risk Rs    = CAPITAL x DEFAULT_RISK_PCT
           = Rs 10,00,000 x 1% = Rs 10,000

Risk/unit  = |Entry - Stop Loss|

Quantity   = floor(Risk Rs / Risk/unit)
```

### Trade CSV columns for risk management

| Column | Description |
|--------|-------------|
| `position_size` | Number of units / lots |
| `risk_inr` | Actual Rs at risk (Qty x risk/unit) |
| `risk_pct` | Actual % of capital at risk |
| `max_profit_1R_inr` | Max profit if T1 hit |
| `max_profit_2R_inr` | Max profit if T2 hit |
| `max_profit_3R_inr` | Max profit if T3 hit |

---

## 📄 Output Files

### 1. `output/trades.csv`

The primary trade file. One row per trade setup, sorted by confidence (highest first).

| Column | Type | Description |
|--------|------|-------------|
| `trade_id` | string | Unique ID (`T0001`, `T0002`, ...) |
| `symbol` | string | Instrument name (`NIFTY 50`) |
| `pattern` | string | Pattern name |
| `direction` | string | `BULLISH` or `BEARISH` |
| `type` | string | `reversal` or `continuation` |
| `pattern_start` | datetime | When the pattern formation began |
| `pattern_end` | datetime | When the pattern completed |
| `entry_price` | float | Suggested entry price |
| `stop_loss` | float | Stop-loss price |
| `target_1R` | float | First target (1.5x risk) |
| `target_2R` | float | Second target (2.5x risk) |
| `target_3R` | float | Third target (4.0x risk) |
| `risk_reward` | float | Actual R:R ratio |
| `position_size` | int | Quantity to trade |
| `risk_inr` | float | Capital at risk in Rs |
| `risk_pct` | float | Capital at risk as % |
| `max_profit_1R_inr` | float | Max P&L if T1 hit |
| `max_profit_2R_inr` | float | Max P&L if T2 hit |
| `max_profit_3R_inr` | float | Max P&L if T3 hit |
| `confidence` | float | Pattern confidence score (0–1) |
| `key_levels` | string | Pattern-specific price levels |
| `notes` | string | Detection details |
| `status` | string | `PENDING` (update manually after execution) |

### 2. `output/report.html`

A **self-contained, dark-themed interactive HTML report** that includes:

- **9 summary cards** — patterns found, bullish/bearish count, avg R:R, avg confidence, total risk Rs
- **3 Chart.js charts** — pattern frequency bar, bullish/bearish doughnut, R:R distribution histogram
- **Sortable trade table** — all trades, click any column header to sort
- **Embedded chart thumbnails** — click to open full-size modal
- **Pattern notes** — detection rationale inline in each row

> Open `report.html` directly in any modern browser — no server needed, all assets are inlined.

### 3. `output/charts/*.png`

Per-pattern dark-themed candlestick charts (120 DPI, 16:9 aspect) showing:

- **Candlesticks** — green (bullish) / red (bearish) with wicks
- **Pattern span** — amber shaded region highlighting the pattern formation
- **Entry level** — dashed blue horizontal line
- **Stop Loss** — dotted red horizontal line
- **Target** — dashed green horizontal line
- **Key levels** — pattern-specific annotations (neckline, peaks, etc.)
- **Volume bars** — bottom panel

---

## ⚙️ Configuration Reference

All parameters are in [`pattern_detector/config.py`](pattern_detector/config.py).

### QuestDB Connection

```python
QUESTDB_HOST  = "http://172.172.1.13:9000"   # QuestDB REST API base URL
QUESTDB_TABLE = "nse_nifty_50"               # Source table name
SYMBOL        = "NIFTY 50"                   # Display name in reports
```

### Analysis Window

```python
LOOKBACK_DAYS = 365        # How many days of history to fetch
TIMEFRAME     = "1min"     # Source data resolution (informational)
RESAMPLE_TO   = "15min"    # Resample target -- affects pattern granularity
                            # Options: "1min","5min","15min","30min","1H","1D"
```

> **Resample guidance:**
> - `15min` -> Intraday swing trading (default)
> - `1H` -> Medium-term position trades
> - `1D` -> Multi-day/swing trades, requires more historical data

### Pattern Detection Thresholds

```python
PIVOT_WINDOW         = 5       # Bars each side to confirm a swing high/low
                                # Higher = larger, more significant patterns
VOLUME_CONFIRM       = True    # Require volume spike on breakout bar
VOLUME_MULT          = 1.3     # Breakout volume >= 1.3x 20-bar average
PRICE_TOLERANCE_PCT  = 0.003   # 0.3% tolerance for matching price levels
                                # (e.g., Double Top peaks must be within 0.3%)
MIN_PATTERN_DEPTH_PCT = 0.004  # 0.4% minimum pattern height vs. price
                                # Filters micro-noise patterns
```

### Trade Setup Parameters

```python
DEFAULT_RISK_REWARD  = 2.0     # Minimum R:R -- patterns below this are skipped
DEFAULT_RISK_PCT     = 0.01    # 1% of capital risked per trade
CAPITAL              = 1_000_000  # Rs 10,00,000 demo capital
SL_BUFFER_PCT        = 0.002   # 0.2% buffer beyond pattern extreme for SL
```

### Tuning Guide

| Goal | Parameter to adjust |
|------|-------------------|
| Find more patterns | Decrease `PRICE_TOLERANCE_PCT`, decrease `MIN_PATTERN_DEPTH_PCT` |
| Find fewer, cleaner patterns | Increase `PIVOT_WINDOW`, increase `MIN_PATTERN_DEPTH_PCT` |
| Higher R:R trades only | Increase `DEFAULT_RISK_REWARD` |
| Tighter stops | Decrease `SL_BUFFER_PCT` |
| Ignore volume | Set `VOLUME_CONFIRM = False` |

---

## 🛠️ Installation & Setup

### Prerequisites

- Python **3.9+**
- Access to QuestDB instance at `http://172.172.1.13:9000`
- Table `nse_nifty_50` with columns: `date` (TIMESTAMP), `open`, `high`, `low`, `close` (DOUBLE), `volume` (LONG)

### Install Dependencies

```bash
pip install pandas numpy requests scipy matplotlib mplfinance
```

All dependencies are standard and widely available:

| Package | Version | Purpose |
|---------|---------|---------|
| `pandas` | >=2.0 | Data manipulation, resampling |
| `numpy` | >=1.23 | Numerical operations |
| `requests` | >=2.28 | QuestDB REST API calls |
| `scipy` | >=1.9 | Swing detection, linear regression |
| `matplotlib` | >=3.6 | Chart rendering |
| `mplfinance` | >=0.12 | Candlestick chart support |

> **Note:** The `questdb` Python package is **not used** — the system connects via QuestDB's built-in `/exec` REST endpoint, which is more portable and requires no extra SDK.

### Verify QuestDB Connection

```bash
python -c "
import requests
r = requests.get('http://172.172.1.13:9000/exec',
                 params={'query': 'SELECT count() FROM nse_nifty_50'})
print(r.json())
"
```

You should see a JSON response with the row count.

---

## 🚀 Running the Pipeline

### Quick Start

```bash
cd market_understanding
python run.py
```

This runs with defaults from `config.py`:
- **15-minute** bars, **last 365 days**, up to **30 charts**

### Full Run with All Charts

```bash
python run.py --max-charts 100
```

### Hourly Timeframe (Swing Trades)

```bash
python run.py --resample 1H --days 365
```

### Fast Run (No Charts)

```bash
python run.py --no-charts
```

### Last 3 Months Only

```bash
python run.py --days 90
```

---

## 🖥️ CLI Arguments

```
usage: run.py [-h] [--resample RESAMPLE] [--days DAYS] [--no-charts] [--max-charts N]

Chart Pattern Detector for NIFTY 50

options:
  -h, --help            Show this help message and exit

  --resample RESAMPLE   Timeframe to resample 1-min data to before analysis.
                        Options: 1min, 5min, 15min, 30min, 1H, 1D
                        Default: value from config.py (15min)

  --days DAYS           Number of calendar days to look back from today.
                        Default: value from config.py (365)

  --no-charts           Skip PNG chart generation. Speeds up the pipeline
                        significantly when you only need the CSV and report.

  --max-charts N        Maximum number of charts to generate (default: 30).
                        Charts are generated for the top-N highest confidence
                        trades.
```

---

## 📦 Module Reference

### `config.py`
Central configuration. **All user-facing settings live here.** Change this file to adjust the instrument, date range, capital, risk parameters, and detection thresholds.

---

### `data_loader.py`

```python
load_ohlcv(lookback_days=365, resample_to="15min") -> pd.DataFrame
```
Fetches data from QuestDB REST API (`/exec` endpoint), parses timestamps to UTC-aware `DatetimeIndex`, casts OHLCV columns, and resamples to the target frequency using standard OHLC aggregation:
- `open`   = first bar
- `high`   = max of period
- `low`    = min of period
- `close`  = last bar
- `volume` = sum of period

```python
get_daily_df(lookback_days=365) -> pd.DataFrame
```
Convenience wrapper that returns daily bars.

---

### `utils.py`

| Function | Signature | Description |
|----------|-----------|-------------|
| `find_swing_highs` | `(df, window) -> np.ndarray` | Indices of local high pivots |
| `find_swing_lows` | `(df, window) -> np.ndarray` | Indices of local low pivots |
| `prices_approx_equal` | `(a, b, tol) -> bool` | Price level equality within tolerance |
| `pct_diff` | `(a, b) -> float` | Absolute % difference between two prices |
| `fit_trendline` | `(x, y) -> (slope, intercept, r)` | Linear regression on price series |
| `volume_spike` | `(df, idx, period, mult) -> bool` | Volume anomaly detection |
| `atr` | `(df, period) -> pd.Series` | Average True Range |
| `rolling_slope` | `(series, window) -> pd.Series` | Normalised rolling slope |

---

### `patterns.py`

Each detector follows the same contract:

```python
detect_<pattern_name>(df: pd.DataFrame) -> List[Dict]
```

Every dict in the returned list contains:

```python
{
    "pattern"    : str,        # e.g. "Head & Shoulders"
    "direction"  : str,        # "bullish" | "bearish"
    "type"       : str,        # "reversal" | "continuation"
    "start_idx"  : int,        # bar index (start of pattern)
    "end_idx"    : int,        # bar index (end of pattern)
    "start_date" : Timestamp,
    "end_date"   : Timestamp,
    "key_levels" : dict,       # pattern-specific prices {label: price}
    "entry"      : float,
    "stop_loss"  : float,
    "target"     : float,
    "risk_reward": float,
    "confidence" : float,      # 0.0 - 1.0
    "notes"      : str,
}
```

**Master runner:**

```python
detect_all_patterns(df: pd.DataFrame) -> pd.DataFrame
```

Runs all 9 detector groups, deduplicates overlapping detections, and returns a single sorted DataFrame.

---

### `trade_generator.py`

```python
build_trade_file(patterns_df: pd.DataFrame) -> pd.DataFrame
```
- Filters patterns below minimum R:R
- Computes T1/T2/T3 targets
- Calculates position size using fixed fractional risk
- Writes `output/trades.csv`
- Returns trades DataFrame

---

### `chart_generator.py`

```python
plot_pattern(df, pattern_row, filename=None) -> str
```
Renders a single dark-themed chart for one pattern. Returns the saved PNG path.

```python
generate_all_charts(df, patterns_df, max_charts=30) -> dict[str, str]
```
Batch renders top-N patterns. Returns `{trade_id -> chart_path}` mapping.

---

### `report_generator.py`

```python
generate_report(patterns_df, trades_df, charts, df_ohlc) -> str
```
Builds a fully self-contained HTML file with embedded Chart.js visualizations and base64-encoded chart images. Returns the path to `report.html`.

---

## 📊 Sample Results (Last 1 Year)

> Run on: **NIFTY 50** · 15-min bars · 30 Oct 2025 -> 30 Oct 2026

### Pattern Breakdown

| Pattern | Count | Direction |
|---------|-------|-----------|
| Bear Flag | 41 | Bearish |
| Bull Flag | 27 | Bullish |
| Cup and Handle | 18 | Bullish |
| Falling Wedge | 11 | Bullish |
| Double Top | 7 | Bearish |
| Inverse Head & Shoulders | 4 | Bullish |
| Rising Wedge | 4 | Bearish |
| Triple Top | 4 | Bearish |
| Ascending Channel | 3 | Bullish |
| Double Bottom | 2 | Bullish |
| Head & Shoulders | 1 | Bearish |
| **Total** | **122** | 65 Bull / 57 Bear |

### Key Metrics

| Metric | Value |
|--------|-------|
| Total Patterns Detected | **122** |
| Bullish Setups | **65** (53%) |
| Bearish Setups | **57** (47%) |
| Reversal Patterns | **33** (27%) |
| Continuation Patterns | **89** (73%) |
| Average Risk:Reward | **3.87x** |
| Raw 1-min Bars Loaded | **92,762** |
| Resampled 15-min Bars | **6,187** |
| Pipeline Runtime | **~11 seconds** |
| Charts Generated | **30 PNGs** |

---

## 🔧 Extending the System

### Adding a New Pattern

1. Open `pattern_detector/patterns.py`
2. Create a new function following the existing contract:

```python
def detect_my_new_pattern(df: pd.DataFrame) -> PatternList:
    results = []
    # ... your detection logic using utils.py helpers ...
    results.append(_base_pattern(
        "My New Pattern", "bullish", "reversal",
        start_idx, end_idx, df,
        {"key_level": price},
        trade_levels,   # from _trade_levels()
        confidence,
        "detection notes"
    ))
    return results
```

3. Register it in the `ALL_DETECTORS` list at the bottom of `patterns.py`:

```python
ALL_DETECTORS = [
    ...
    ("My New Pattern", detect_my_new_pattern),
]
```

### Changing the Instrument

Update `config.py`:

```python
QUESTDB_TABLE = "your_table_name"
SYMBOL        = "YOUR SYMBOL"
```

Make sure your table has columns: `date`, `open`, `high`, `low`, `close`, `volume`.

### Adding a New Timeframe

Pass it via CLI:

```bash
python run.py --resample 30min
```

Or set it permanently in `config.py`:

```python
RESAMPLE_TO = "30min"
```

### Scheduling Automated Runs

Use Windows Task Scheduler:

```batch
REM Run at market open (9:20 AM IST) -- quick CSV only
python D:\projects-shubham\...\market_understanding\run.py --no-charts

REM End of day full report
python D:\projects-shubham\...\market_understanding\run.py --max-charts 50
```

---

## 🐛 Troubleshooting

### `No data returned from QuestDB`
- Verify the QuestDB host is reachable: `ping 172.172.1.13`
- Check the table name matches: `QUESTDB_TABLE = "nse_nifty_50"`
- Confirm the date range has data — try reducing `--days`

### `No patterns detected`
- Loosen thresholds in `config.py`:
  ```python
  PIVOT_WINDOW          = 3      # was 5
  PRICE_TOLERANCE_PCT   = 0.006  # was 0.003
  MIN_PATTERN_DEPTH_PCT = 0.002  # was 0.004
  VOLUME_CONFIRM        = False  # disable volume filter
  ```
- Try a different timeframe: `--resample 1H`

### `UnicodeEncodeError` on Windows PowerShell

Set the encoding environment variable before running:

```powershell
$env:PYTHONIOENCODING='utf-8'; python run.py
```

### Charts are empty / rendering black

- Ensure the `output/charts/` directory is writable
- The `Agg` (non-interactive) matplotlib backend is set automatically in `chart_generator.py` — do not change it

### Very slow data fetch

- Reduce `--days` to limit the query window
- Ensure `date` is the designated timestamp column in QuestDB for fast range scans:
  ```sql
  -- Check in QuestDB console
  SHOW COLUMNS FROM nse_nifty_50;
  ```

---

## 📝 Notes & Limitations

- **No backtesting** — this system detects patterns in historical data and generates forward-looking setups, but does not backtest win rate or P&L
- **Intraday patterns** — 15-min timeframe captures intraday swings; adjust to `1D` for multi-day patterns
- **Price targets are projections** — pattern height is projected from the breakout level; actual price behavior may differ
- **All trades start as `PENDING`** — manually update the `status` column in `trades.csv` as trades resolve:
  - `OPEN` — trade is live
  - `HIT_T1` — first target reached
  - `HIT_T2` — second target reached
  - `HIT_T3` — third target reached
  - `STOPPED` — stop loss triggered
  - `CANCELLED` — pattern invalidated before entry
- **Not financial advice** — this tool is for educational and analytical purposes only

---

## 📜 Pattern Reference (TheChartGuys Framework)

| Pattern | Ideal Context | Typical R:R | Notes |
|---------|--------------|-------------|-------|
| Head & Shoulders | Uptrend reversal | 2–4x | Most reliable reversal signal |
| Inverse H&S | Downtrend reversal | 2–4x | Mirror of H&S |
| Double Top | Uptrend reversal | 1.5–3x | Two equal peaks, sell on neckline break |
| Double Bottom | Downtrend reversal | 1.5–3x | Two equal troughs, buy on neckline break |
| Triple Top | Strong resistance | 2–5x | Higher conviction than double top |
| Triple Bottom | Strong support | 2–5x | Higher conviction than double bottom |
| Rising Wedge | Uptrend / overbought | 2–4x | Bearish despite upward slope |
| Falling Wedge | Downtrend / oversold | 2–5x | Bullish, often explosive breakout |
| Bull Flag | Strong uptrend | 1.5–3x | Pole height = target projection |
| Bear Flag | Strong downtrend | 1.5–3x | Mirror of bull flag |
| Bull Pennant | Strong uptrend | 1.5–3x | Tighter consolidation than flag |
| Bear Pennant | Strong downtrend | 1.5–3x | Mirror of bull pennant |
| Ascending Triangle | Uptrend | 1.5–3x | Flat top = strong resistance to break |
| Descending Triangle | Downtrend | 1.5–3x | Flat bottom = strong support to break |
| Symmetrical Triangle | Either direction | 1.5–2.5x | Break follows prior trend direction |
| Ascending Channel | Uptrend | 1.5–2.5x | Buy at lower support line |
| Descending Channel | Downtrend | 1.5–2.5x | Sell at upper resistance line |
| Cup and Handle | Uptrend recovery | 2–5x | Longer formation = more reliable |

---

*Built for the Indian equity market — NSE NIFTY 50 · QuestDB · Python 3.13*
*Pattern framework based on [TheChartGuys.com](https://www.chartguys.com) Chart Pattern Cheat Sheet*
