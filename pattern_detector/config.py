"""
Configuration for Chart Pattern Detection System
QuestDB connection and analysis parameters
"""

# ─── QuestDB Connection ────────────────────────────────────────────────────────
QUESTDB_HOST = "http://172.172.1.13:9000"
QUESTDB_TABLE = "nse_nifty_50"
SYMBOL = "NIFTY 50"

# ─── Analysis Window ──────────────────────────────────────────────────────────
# LOOKBACK_DAYS = 365          # Last 1 year
LOOKBACK_DAYS = 1000          # Last 1 year
TIMEFRAME = "1min"           # Source resolution
# RESAMPLE_TO = "15min"        # Resample 1-min → 15-min for cleaner pattern detection
                              # Options: "1min", "5min", "15min", "30min", "1H", "1D"
RESAMPLE_TO = "1min"        # Resample 1-min → 15-min for cleaner pattern detection
                              # Options: "1min", "5min", "15min", "30min", "1H", "1D"

# ─── Pattern Detection Parameters ────────────────────────────────────────────
PIVOT_WINDOW        = 5       # Candles each side to confirm a swing high/low
VOLUME_CONFIRM      = True    # Require volume spike on breakout
VOLUME_MULT         = 1.3     # Breakout volume must be N× 20-period avg

# Tolerance for matching price levels (% of price)
PRICE_TOLERANCE_PCT = 0.003   # 0.3 %

# Minimum pattern "depth" as % of price (filters tiny noise patterns)
MIN_PATTERN_DEPTH_PCT = 0.004  # 0.4 %

# ─── Trade Setup Parameters ───────────────────────────────────────────────────
DEFAULT_RISK_REWARD  = 2.0    # Minimum R:R to take a trade
DEFAULT_RISK_PCT     = 0.01   # Risk 1 % of capital per trade
CAPITAL              = 1_000_000  # ₹ 10 Lakh demo capital

# Stop-loss offsets (as fraction of pattern range)
SL_BUFFER_PCT        = 0.002  # 0.2 % beyond pattern extreme

# ─── Output Paths ─────────────────────────────────────────────────────────────
import os, pathlib
BASE_DIR    = pathlib.Path(__file__).parent
OUTPUT_DIR  = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TRADE_FILE  = str(OUTPUT_DIR / "trades.csv")
REPORT_FILE = str(OUTPUT_DIR / "report.html")
CHART_DIR   = str(OUTPUT_DIR / "charts")
os.makedirs(CHART_DIR, exist_ok=True)
