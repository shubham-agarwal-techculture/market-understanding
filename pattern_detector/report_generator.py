"""
HTML Report Generator
=====================
Creates a rich, dark-themed, fully self-contained HTML report with:
  - Executive summary cards
  - Pattern distribution charts (Chart.js)
  - Trade table with sortable columns
  - Per-pattern candlestick chart thumbnails
  - Risk dashboard
"""
from __future__ import annotations

import os, sys, json
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from pattern_detector.config import SYMBOL, CAPITAL, REPORT_FILE
from pattern_detector.utils import session_bounds


def _direction_badge(direction: str) -> str:
    if direction.lower() == "bullish":
        return '<span class="badge bull">▲ BULLISH</span>'
    return '<span class="badge bear">▼ BEARISH</span>'


def _type_badge(ptype: str) -> str:
    cls = "rev" if "reversal" in ptype.lower() else "cont"
    return f'<span class="badge {cls}">{ptype.upper()}</span>'


def _conf_bar(conf: float) -> str:
    pct = int(conf * 100)
    color = "#26a641" if pct >= 70 else "#e3b341" if pct >= 50 else "#f85149"
    return (
        f'<div class="conf-bar-bg"><div class="conf-bar" '
        f'style="width:{pct}%;background:{color}"></div></div>'
        f'<small style="color:{color}">{pct}%</small>'
    )


def _unix(ts) -> int:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return int(t.timestamp())


def _match_key(pattern, start, entry) -> tuple:
    return (str(pattern), str(start)[:19], round(float(entry), 2))


def _compress_window(sl: pd.DataFrame, max_bars: int = 1200) -> pd.DataFrame:
    """Bucket a long window so the interactive chart stays responsive."""
    n = len(sl)
    if n <= max_bars:
        return sl
    step = int(np.ceil(n / max_bars))
    rows = []
    idx = []
    for i in range(0, n, step):
        chunk = sl.iloc[i:i + step]
        rows.append({
            "open": float(chunk["open"].iloc[0]),
            "high": float(chunk["high"].max()),
            "low": float(chunk["low"].min()),
            "close": float(chunk["close"].iloc[-1]),
            "volume": float(chunk["volume"].sum()),
        })
        idx.append(chunk.index[0])
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx))


def _price_lines(trade: pd.Series) -> list:
    specs = [
        ("Entry", trade.get("entry_price"), "#388bfd"),
        ("Stop", trade.get("stop_loss"), "#f85149"),
        ("T1", trade.get("target_1R"), "#26a641"),
        ("T2", trade.get("target_2R"), "#3fb950"),
        ("T3", trade.get("target_3R"), "#56d364"),
    ]
    lines = []
    for name, value, color in specs:
        try:
            price = float(value)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(price):
            continue
        lines.append([name, round(price, 2), color])
    return lines


def _build_chart_payload(
    patterns_df: pd.DataFrame,
    trades_df: pd.DataFrame,
    df_ohlc: pd.DataFrame | None,
) -> dict:
    """OHLC windows keyed by trade id, for the interactive chart."""
    if df_ohlc is None or df_ohlc.empty or patterns_df.empty or trades_df.empty:
        return {}
    if "start_idx" not in patterns_df.columns or "end_idx" not in patterns_df.columns:
        return {}

    by_key: dict[tuple, pd.Series] = {}
    for _, tr in trades_df.iterrows():
        try:
            key = _match_key(tr.get("pattern"), tr.get("pattern_start"), tr.get("entry_price"))
        except (TypeError, ValueError):
            continue
        by_key[key] = tr

    payload: dict[str, dict] = {}
    ctx = 50
    for _, pat in patterns_df.iterrows():
        try:
            key = _match_key(pat.get("pattern"), pat.get("start_date"), pat.get("entry"))
        except (TypeError, ValueError):
            continue
        trade = by_key.get(key)
        if trade is None:
            continue

        start_idx = int(pat["start_idx"])
        end_idx = int(pat["end_idx"])
        day_s, day_e = session_bounds(df_ohlc.index, start_idx)
        s = max(day_s, start_idx - ctx)
        e = min(day_e, end_idx + ctx)
        window = _compress_window(df_ohlc.iloc[s:e + 1])
        if window.empty:
            continue

        candles = []
        volume = []
        labels = []
        real_times = []
        # Bar slots are packed together so overnight gaps do not split the pattern.
        for ts, row in window.iterrows():
            o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
            if not all(np.isfinite(v) for v in (o, h, l, c)):
                continue
            real_times.append(_unix(ts))
            slot = 1_700_000_000 + len(candles) * 60
            labels.append(pd.Timestamp(ts).strftime("%d %b %H:%M"))
            candles.append([slot, round(o, 2), round(h, 2), round(l, 2), round(c, 2)])
            up = 1 if c >= o else 0
            volume.append([slot, int(row["volume"]), up])

        if len(candles) < 2:
            continue

        def _slot_for(target: int) -> int:
            j = min(range(len(real_times)), key=lambda i: abs(real_times[i] - target))
            return 1_700_000_000 + j * 60

        mark_start = _slot_for(_unix(df_ohlc.index[start_idx]))
        mark_end = _slot_for(_unix(df_ohlc.index[end_idx]))

        tid = str(trade.get("trade_id"))
        direction = str(trade.get("direction", "")).upper()
        payload[tid] = {
            "title": f"{tid}  ·  {trade.get('pattern')}  ·  {direction}",
            "sub": (
                f"Entry ₹{float(trade.get('entry_price', 0)):,.2f}"
                f"   Stop ₹{float(trade.get('stop_loss', 0)):,.2f}"
                f"   T1 ₹{float(trade.get('target_1R', 0)):,.2f}"
                f"   T2 ₹{float(trade.get('target_2R', 0)):,.2f}"
                f"   T3 ₹{float(trade.get('target_3R', 0)):,.2f}"
            ),
            "candles": candles,
            "labels": labels,
            "volume": volume,
            "lines": _price_lines(trade),
            "marks": [mark_start, mark_end],
        }
    return payload


def generate_report(
    patterns_df: pd.DataFrame,
    trades_df: pd.DataFrame,
    charts: dict[str, str],
    df_ohlc: pd.DataFrame | None = None,
) -> str:
    """Build and save the HTML report. Returns the output path."""

    now_str = datetime.now().strftime("%d %b %Y  %H:%M:%S")

    # ── Stats ──────────────────────────────────────────────────────────────────
    n_patterns  = len(patterns_df)
    n_bullish   = int((patterns_df["direction"] == "bullish").sum()) if n_patterns else 0
    n_bearish   = n_patterns - n_bullish
    n_reversal  = int((patterns_df["type"] == "reversal").sum()) if n_patterns else 0
    n_cont      = n_patterns - n_reversal
    n_trades    = len(trades_df)
    avg_rr      = round(trades_df["risk_reward"].mean(), 2) if n_trades else 0
    avg_conf    = round(trades_df["confidence"].mean() * 100, 1) if n_trades else 0
    total_risk  = round(trades_df["risk_inr"].sum(), 2) if n_trades else 0

    # ── Chart.js data ─────────────────────────────────────────────────────────
    pattern_counts = patterns_df["pattern"].value_counts().to_dict() if n_patterns else {}
    pc_labels = json.dumps(list(pattern_counts.keys()))
    pc_data   = json.dumps(list(pattern_counts.values()))

    dir_data  = json.dumps([n_bullish, n_bearish])
    rr_vals   = trades_df["risk_reward"].tolist() if n_trades else []
    rr_data   = json.dumps(rr_vals)

    # ── Interactive chart windows (replaces PNG snapshots) ───────────────────
    chart_payload = _build_chart_payload(patterns_df, trades_df, df_ohlc)
    chart_json = json.dumps(chart_payload, separators=(",", ":")).replace("<", "\\u003c")

    # ── Trade rows HTML ───────────────────────────────────────────────────────
    trade_rows = ""
    if n_trades:
        for _, tr in trades_df.iterrows():
            tid   = tr.get("trade_id", "—")
            thumb_html = "—"
            if str(tid) in chart_payload:
                thumb_html = (
                    f'<button type="button" class="chart-btn" '
                    f'onclick="openChart(\'{tid}\')">View chart</button>'
                )

            rr   = tr.get("risk_reward", 0)
            conf = tr.get("confidence", 0)
            rr_color = "#26a641" if rr >= 2.5 else "#e3b341" if rr >= 1.5 else "#f85149"

            trade_rows += f"""
            <tr>
              <td><strong>{tid}</strong></td>
              <td>{tr.get("pattern","—")}</td>
              <td>{_direction_badge(tr.get("direction","").lower())}</td>
              <td>{_type_badge(tr.get("type",""))}</td>
              <td>₹{tr.get("entry_price",0):,.2f}</td>
              <td style="color:#f85149">₹{tr.get("stop_loss",0):,.2f}</td>
              <td style="color:#26a641">₹{tr.get("target_1R",0):,.2f}</td>
              <td style="color:#26a641">₹{tr.get("target_2R",0):,.2f}</td>
              <td style="color:#26a641">₹{tr.get("target_3R",0):,.2f}</td>
              <td style="color:{rr_color}"><strong>{rr:.1f}x</strong></td>
              <td>{tr.get("position_size",0):,}</td>
              <td>₹{tr.get("risk_inr",0):,.0f}</td>
              <td>{_conf_bar(float(conf))}</td>
              <td class="notes-cell">{tr.get("notes","")[:80]}</td>
              <td>{thumb_html}</td>
            </tr>"""

    # ── Data range info ───────────────────────────────────────────────────────
    data_range = ""
    if df_ohlc is not None and len(df_ohlc) > 0:
        data_range = f"{str(df_ohlc.index[0])[:10]} → {str(df_ohlc.index[-1])[:10]}  ({len(df_ohlc):,} bars)"

    # ── HTML ──────────────────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{SYMBOL} – Chart Pattern Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #0d1117; --surface: #161b22; --border: #21262d;
    --text: #c9d1d9; --muted: #8b949e; --accent: #388bfd;
    --green: #26a641; --red: #f85149; --gold: #e3b341;
    --radius: 10px; --shadow: 0 4px 24px rgba(0,0,0,0.5);
  }}
  body {{ font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text);
         font-size: 13px; min-height: 100vh; }}
  header {{ background: linear-gradient(135deg,#161b22,#0d1117);
            border-bottom: 1px solid var(--border); padding: 24px 40px;
            display: flex; align-items: center; justify-content: space-between; }}
  header h1 {{ font-size: 22px; font-weight: 700; color: #fff; letter-spacing: -0.5px; }}
  header h1 span {{ color: var(--accent); }}
  header .meta {{ color: var(--muted); font-size: 11px; text-align: right; line-height: 1.8; }}
  main {{ max-width: 1600px; margin: 0 auto; padding: 30px 40px; }}

  /* ── Summary Cards ── */
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(160px,1fr)); gap: 14px; margin-bottom: 30px; }}
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
           padding: 18px; text-align: center; box-shadow: var(--shadow); transition: transform .2s; }}
  .card:hover {{ transform: translateY(-3px); }}
  .card .val {{ font-size: 30px; font-weight: 700; margin-bottom: 6px; }}
  .card .lbl {{ color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .5px; }}
  .card.bull .val {{ color: var(--green); }}
  .card.bear .val {{ color: var(--red); }}
  .card.gold .val {{ color: var(--gold); }}
  .card.blue .val {{ color: var(--accent); }}

  /* ── Charts Row ── */
  .charts-grid {{ display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 18px; margin-bottom: 30px; }}
  .chart-box {{ background: var(--surface); border: 1px solid var(--border);
                border-radius: var(--radius); padding: 18px; box-shadow: var(--shadow); }}
  .chart-box h3 {{ font-size: 12px; text-transform: uppercase; letter-spacing: .5px;
                   color: var(--muted); margin-bottom: 14px; }}
  .chart-box canvas {{ max-height: 220px; }}

  /* ── Section ── */
  .section {{ background: var(--surface); border: 1px solid var(--border);
              border-radius: var(--radius); padding: 20px; margin-bottom: 24px;
              box-shadow: var(--shadow); }}
  .section h2 {{ font-size: 15px; font-weight: 600; margin-bottom: 16px;
                 color: #fff; border-bottom: 1px solid var(--border); padding-bottom: 10px; }}

  /* ── Table ── */
  .tbl-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  thead tr {{ background: #1c2128; }}
  th {{ padding: 10px 12px; text-align: left; color: var(--muted); font-weight: 500;
        text-transform: uppercase; font-size: 10px; letter-spacing: .5px;
        cursor: pointer; user-select: none; white-space: nowrap; }}
  th:hover {{ color: var(--text); }}
  td {{ padding: 9px 12px; border-bottom: 1px solid var(--border); vertical-align: middle; }}
  tr:hover td {{ background: #1c2128; }}
  .notes-cell {{ color: var(--muted); font-size: 11px; max-width: 200px;
                 white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}

  /* ── Badges ── */
  .badge {{ border-radius: 4px; padding: 2px 7px; font-size: 10px; font-weight: 600; white-space: nowrap; }}
  .badge.bull {{ background: rgba(38,166,65,.2); color: #26a641; }}
  .badge.bear {{ background: rgba(248,81,73,.2); color: #f85149; }}
  .badge.rev  {{ background: rgba(227,179,65,.15); color: #e3b341; }}
  .badge.cont {{ background: rgba(56,139,253,.15); color: #388bfd; }}

  /* ── Confidence bar ── */
  .conf-bar-bg {{ background: #21262d; border-radius: 3px; height: 5px; margin-bottom: 3px; }}
  .conf-bar    {{ height: 5px; border-radius: 3px; transition: width .4s; }}

  /* ── Interactive chart ── */
  .chart-btn {{ background:#21262d; color:var(--text); border:1px solid var(--accent);
                border-radius:5px; padding:5px 10px; cursor:pointer; font-size:11px;
                font-weight:600; font-family:inherit; white-space:nowrap; }}
  .chart-btn:hover {{ background:var(--accent); color:#fff; }}
  .modal-overlay {{ display:none; position:fixed; inset:0; background:rgba(0,0,0,.88);
                    z-index:1000; align-items:center; justify-content:center; padding:24px; }}
  .modal-overlay.active {{ display:flex; }}
  .chart-panel {{ width:min(1200px, 96vw); height:min(820px, 92vh); background:var(--bg);
                  border:1px solid var(--border); border-radius:12px;
                  box-shadow:0 0 60px rgba(0,0,0,.9); display:flex; flex-direction:column;
                  overflow:hidden; }}
  .chart-panel.is-max {{ position:fixed; inset:0; width:100vw; height:100vh;
                         max-width:none; max-height:none; border-radius:0; z-index:1100; }}
  .chart-head {{ display:flex; align-items:center; justify-content:space-between; gap:16px;
                 padding:14px 16px; border-bottom:1px solid var(--border); background:var(--surface); }}
  .chart-head h3 {{ color:#fff; font-size:14px; font-weight:600; }}
  .chart-head p {{ color:var(--muted); font-size:11px; margin-top:4px; }}
  .chart-actions {{ display:flex; gap:8px; flex-shrink:0; }}
  .chart-actions button {{ background:#21262d; color:var(--text); border:1px solid var(--border);
                           border-radius:6px; padding:6px 12px; cursor:pointer; font-family:inherit;
                           font-size:12px; font-weight:600; }}
  .chart-actions button:hover {{ border-color:var(--accent); color:#fff; }}
  #lw-chart {{ flex:1; min-height:0; width:100%; }}

  /* ── Scrollbar ── */
  ::-webkit-scrollbar {{ width:6px; height:6px; }}
  ::-webkit-scrollbar-thumb {{ background: var(--border); border-radius:3px; }}

  /* ── Footer ── */
  footer {{ text-align:center; padding:20px; color:var(--muted); font-size:11px; }}
</style>
</head>
<body>

<header>
  <div>
    <h1>📊 <span>{SYMBOL}</span> – Chart Pattern Analysis</h1>
    <p style="color:var(--muted);font-size:12px;margin-top:4px">
      Powered by TheChartGuys Pattern Framework · QuestDB · 1-min OHLCV · Intraday only
    </p>
  </div>
  <div class="meta">
    Generated: {now_str}<br>
    Data Range: {data_range}<br>
    Capital: ₹{CAPITAL:,.0f}
  </div>
</header>

<main>

<!-- ── Summary Cards ─────────────────────────────────────────────────────── -->
<div class="cards">
  <div class="card blue">
    <div class="val">{n_patterns}</div>
    <div class="lbl">Patterns Found</div>
  </div>
  <div class="card blue">
    <div class="val">{n_trades}</div>
    <div class="lbl">Trade Setups</div>
  </div>
  <div class="card bull">
    <div class="val">{n_bullish}</div>
    <div class="lbl">Bullish Signals</div>
  </div>
  <div class="card bear">
    <div class="val">{n_bearish}</div>
    <div class="lbl">Bearish Signals</div>
  </div>
  <div class="card gold">
    <div class="val">{n_reversal}</div>
    <div class="lbl">Reversal Patterns</div>
  </div>
  <div class="card blue">
    <div class="val">{n_cont}</div>
    <div class="lbl">Continuation Patterns</div>
  </div>
  <div class="card gold">
    <div class="val">{avg_rr}x</div>
    <div class="lbl">Avg Risk:Reward</div>
  </div>
  <div class="card gold">
    <div class="val">{avg_conf}%</div>
    <div class="lbl">Avg Confidence</div>
  </div>
  <div class="card bear">
    <div class="val">₹{total_risk:,.0f}</div>
    <div class="lbl">Total Capital at Risk</div>
  </div>
</div>

<!-- ── Analytics Charts ─────────────────────────────────────────────────── -->
<div class="charts-grid">
  <div class="chart-box">
    <h3>Pattern Frequency</h3>
    <canvas id="patternChart"></canvas>
  </div>
  <div class="chart-box">
    <h3>Bullish vs Bearish</h3>
    <canvas id="dirChart"></canvas>
  </div>
  <div class="chart-box">
    <h3>Risk:Reward Distribution</h3>
    <canvas id="rrChart"></canvas>
  </div>
</div>

<!-- ── Trade Setups Table ─────────────────────────────────────────────────── -->
<div class="section">
  <h2>🎯 Trade Setups</h2>
  <div class="tbl-wrap">
    <table id="tradeTable">
      <thead>
        <tr>
          <th onclick="sortTable(0)">ID ↕</th>
          <th onclick="sortTable(1)">Pattern ↕</th>
          <th onclick="sortTable(2)">Direction ↕</th>
          <th onclick="sortTable(3)">Type ↕</th>
          <th onclick="sortTable(4)">Entry ↕</th>
          <th onclick="sortTable(5)">Stop Loss ↕</th>
          <th>Target 1R</th>
          <th>Target 2R</th>
          <th>Target 3R</th>
          <th onclick="sortTable(9)">R:R ↕</th>
          <th>Qty</th>
          <th>Risk ₹</th>
          <th onclick="sortTable(12)">Confidence ↕</th>
          <th>Notes</th>
          <th>Chart</th>
        </tr>
      </thead>
      <tbody>
        {trade_rows if trade_rows else '<tr><td colspan="15" style="text-align:center;color:var(--muted);padding:30px">No trade setups generated</td></tr>'}
      </tbody>
    </table>
  </div>
</div>

</main>

<!-- ── Maximizable candlestick chart ─────────────────────────────────────── -->
<div class="modal-overlay" id="chart-modal" onclick="if(event.target===this) closeChart(true)">
  <div class="chart-panel" id="chart-panel" role="dialog" aria-modal="true" aria-labelledby="chart-title">
    <div class="chart-head">
      <div>
        <h3 id="chart-title">Chart</h3>
        <p id="chart-sub"></p>
      </div>
      <div class="chart-actions">
        <button type="button" id="max-btn" onclick="toggleMaximize()">Maximize</button>
        <button type="button" onclick="closeChart(true)">Close</button>
      </div>
    </div>
    <div id="lw-chart"></div>
  </div>
</div>

<footer>
  Chart Pattern Analysis System · {SYMBOL} · {now_str} ·
  Patterns based on <a href="https://www.chartguys.com" style="color:var(--accent)">TheChartGuys.com</a>
</footer>

<script>
// ── Chart.js ─────────────────────────────────────────────────────────────────
Chart.defaults.color = '#8b949e';
Chart.defaults.borderColor = '#21262d';

// Pattern Frequency
new Chart(document.getElementById('patternChart'), {{
  type: 'bar',
  data: {{
    labels: {pc_labels},
    datasets: [{{ label: 'Count', data: {pc_data},
      backgroundColor: '#388bfd44', borderColor: '#388bfd',
      borderWidth: 1.5, borderRadius: 4 }}]
  }},
  options: {{ plugins: {{ legend: {{ display: false }} }},
    scales: {{ x: {{ ticks: {{ maxRotation: 30, font: {{ size: 9 }} }} }},
               y: {{ ticks: {{ font: {{ size: 9 }} }} }} }} }}
}});

// Direction Doughnut
new Chart(document.getElementById('dirChart'), {{
  type: 'doughnut',
  data: {{
    labels: ['Bullish', 'Bearish'],
    datasets: [{{ data: {dir_data},
      backgroundColor: ['#26a64180','#f8514980'],
      borderColor: ['#26a641','#f85149'], borderWidth: 2 }}]
  }},
  options: {{ cutout: '60%', plugins: {{ legend: {{ position: 'bottom', labels: {{ font: {{ size: 10 }} }} }} }} }}
}});

// R:R Histogram
const rrVals = {rr_data};
const bins = [0,1,1.5,2,2.5,3,4,10];
const hist = Array(bins.length-1).fill(0);
rrVals.forEach(v => {{ for(let i=0;i<bins.length-1;i++) {{ if(v>=bins[i]&&v<bins[i+1]) {{ hist[i]++; break; }} }} }});
const rrLabels = bins.slice(0,-1).map((b,i)=>`${{b}}-${{bins[i+1]}}`);
new Chart(document.getElementById('rrChart'), {{
  type: 'bar',
  data: {{
    labels: rrLabels,
    datasets: [{{ label: 'Trades', data: hist,
      backgroundColor: '#e3b34140', borderColor: '#e3b341',
      borderWidth: 1.5, borderRadius: 4 }}]
  }},
  options: {{ plugins: {{ legend: {{ display: false }} }},
    scales: {{ x: {{ ticks: {{ font: {{ size: 9 }} }} }},
               y: {{ ticks: {{ font: {{ size: 9 }}, stepSize: 1 }} }} }} }}
}});

// ── Interactive candlestick chart ─────────────────────────────────────────────
const CHARTS = {chart_json};
let lwChart = null;
let lwResize = null;

function destroyChart() {{
  if (lwResize) {{ lwResize.disconnect(); lwResize = null; }}
  if (lwChart) {{ lwChart.remove(); lwChart = null; }}
}}

function fitChart() {{
  if (!lwChart) return;
  const el = document.getElementById('lw-chart');
  lwChart.resize(el.clientWidth, el.clientHeight);
}}

function renderChart(spec) {{
  destroyChart();
  const el = document.getElementById('lw-chart');
  if (typeof LightweightCharts === 'undefined') {{
    el.innerHTML = '<p style="padding:24px;color:#f85149">Chart library failed to load. Check your network connection and reload the report.</p>';
    return;
  }}
  el.innerHTML = '';
  const labelByTime = {{}};
  spec.candles.forEach((c, i) => {{ labelByTime[c[0]] = (spec.labels && spec.labels[i]) || ''; }});
  lwChart = LightweightCharts.createChart(el, {{
    autoSize: true,
    layout: {{ background: {{ color: '#0d1117' }}, textColor: '#c9d1d9' }},
    grid: {{ vertLines: {{ color: '#21262d' }}, horzLines: {{ color: '#21262d' }} }},
    rightPriceScale: {{ borderColor: '#21262d' }},
    localization: {{ timeFormatter: (time) => labelByTime[time] || '' }},
    timeScale: {{
      borderColor: '#21262d',
      timeVisible: true,
      secondsVisible: false,
      tickMarkFormatter: (time) => labelByTime[time] || '',
    }},
    crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
  }});
  const candles = lwChart.addCandlestickSeries({{
    upColor: '#26a641', downColor: '#f85149',
    borderUpColor: '#26a641', borderDownColor: '#f85149',
    wickUpColor: '#26a641', wickDownColor: '#f85149',
  }});
  candles.setData(spec.candles.map(c => ({{
    time: c[0], open: c[1], high: c[2], low: c[3], close: c[4]
  }})));
  (spec.lines || []).forEach(line => {{
    candles.createPriceLine({{
      price: line[1], color: line[2], lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      axisLabelVisible: true, title: line[0],
    }});
  }});
  if (spec.marks && spec.marks.length === 2) {{
    candles.setMarkers([
      {{ time: spec.marks[0], position: 'aboveBar', color: '#e3b341', shape: 'arrowDown', text: 'Start' }},
      {{ time: spec.marks[1], position: 'aboveBar', color: '#e3b341', shape: 'arrowDown', text: 'End' }},
    ]);
  }}
  const hasVolume = (spec.volume || []).some(v => v[1] > 0);
  if (hasVolume) {{
    const volume = lwChart.addHistogramSeries({{
      priceFormat: {{ type: 'volume' }},
      priceScaleId: 'vol',
    }});
    volume.setData(spec.volume.map(v => ({{
      time: v[0], value: v[1], color: v[2] ? '#26a64188' : '#f8514988'
    }})));
    lwChart.priceScale('vol').applyOptions({{ scaleMargins: {{ top: 0.82, bottom: 0 }} }});
  }}
  lwChart.timeScale().fitContent();
  lwResize = new ResizeObserver(() => fitChart());
  lwResize.observe(el);
}}

function openChart(id) {{
  const spec = CHARTS[id];
  if (!spec) return;
  document.getElementById('chart-title').textContent = spec.title;
  document.getElementById('chart-sub').textContent = spec.sub;
  document.getElementById('chart-modal').classList.add('active');
  document.body.style.overflow = 'hidden';
  requestAnimationFrame(() => renderChart(spec));
}}

function restoreChart() {{
  const panel = document.getElementById('chart-panel');
  panel.classList.remove('is-max');
  document.getElementById('max-btn').textContent = 'Maximize';
  if (document.fullscreenElement) document.exitFullscreen();
  setTimeout(fitChart, 60);
}}

function closeChart(force) {{
  const panel = document.getElementById('chart-panel');
  const open = document.getElementById('chart-modal').classList.contains('active');
  if (!open) return;
  const maximized = panel.classList.contains('is-max') || !!document.fullscreenElement;
  if (maximized && !force) {{
    restoreChart();
    return;
  }}
  panel.classList.remove('is-max');
  document.getElementById('max-btn').textContent = 'Maximize';
  if (document.fullscreenElement) document.exitFullscreen();
  document.getElementById('chart-modal').classList.remove('active');
  document.body.style.overflow = '';
  destroyChart();
}}

function toggleMaximize() {{
  const panel = document.getElementById('chart-panel');
  const on = !panel.classList.contains('is-max');
  panel.classList.toggle('is-max', on);
  document.getElementById('max-btn').textContent = on ? 'Restore' : 'Maximize';
  if (on && panel.requestFullscreen) {{
    panel.requestFullscreen().catch(() => {{}});
  }} else if (!on && document.fullscreenElement) {{
    document.exitFullscreen();
  }}
  setTimeout(fitChart, 60);
}}

document.addEventListener('fullscreenchange', () => {{
  const panel = document.getElementById('chart-panel');
  if (!document.fullscreenElement && panel.classList.contains('is-max')) {{
    panel.classList.remove('is-max');
    document.getElementById('max-btn').textContent = 'Maximize';
  }}
  setTimeout(fitChart, 60);
}});
document.addEventListener('keydown', e => {{ if (e.key === 'Escape') closeChart(false); }});

// ── Table sort ────────────────────────────────────────────────────────────────
function sortTable(col) {{
  const table = document.getElementById('tradeTable');
  const tbody = table.tBodies[0];
  const rows  = Array.from(tbody.rows);
  const asc   = table.dataset.sortCol == col && table.dataset.sortDir === 'asc';
  rows.sort((a, b) => {{
    let av = a.cells[col]?.innerText.replace(/[₹,%x]/g,'').trim();
    let bv = b.cells[col]?.innerText.replace(/[₹,%x]/g,'').trim();
    const an = parseFloat(av), bn = parseFloat(bv);
    if (!isNaN(an) && !isNaN(bn)) return asc ? bn - an : an - bn;
    return asc ? bv.localeCompare(av) : av.localeCompare(bv);
  }});
  rows.forEach(r => tbody.appendChild(r));
  table.dataset.sortCol = col;
  table.dataset.sortDir = asc ? 'desc' : 'asc';
}}
</script>
</body>
</html>"""

    Path(REPORT_FILE).write_text(html, encoding="utf-8")
    print(f"[report] ✅  HTML report saved → {REPORT_FILE}")
    return REPORT_FILE
