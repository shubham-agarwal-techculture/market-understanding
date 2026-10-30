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

import os, sys, base64, json
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from pattern_detector.config import SYMBOL, CAPITAL, REPORT_FILE


def _img_to_b64(path: str) -> str:
    """Encode image file to base64 for embedding."""
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return ""


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

    # ── Trade rows HTML ───────────────────────────────────────────────────────
    trade_rows = ""
    if n_trades:
        for _, tr in trades_df.iterrows():
            tid   = tr.get("trade_id", "—")
            chart_path = charts.get(str(tid), "")
            thumb_html = ""
            if chart_path and os.path.exists(chart_path):
                b64 = _img_to_b64(chart_path)
                if b64:
                    thumb_html = (
                        f'<img src="data:image/png;base64,{b64}" '
                        f'class="thumb" onclick="openModal(this)" />'
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
  canvas {{ max-height: 220px !important; }}

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

  /* ── Thumbnails / Modal ── */
  .thumb {{ width: 110px; height: 65px; object-fit: cover; border-radius: 5px;
            cursor: pointer; border: 1px solid var(--border); transition: transform .2s; }}
  .thumb:hover {{ transform: scale(1.08); border-color: var(--accent); }}
  .modal-overlay {{ display:none; position:fixed; inset:0; background:rgba(0,0,0,.88);
                    z-index:1000; align-items:center; justify-content:center; }}
  .modal-overlay.active {{ display:flex; }}
  .modal-overlay img {{ max-width:92vw; max-height:88vh; border-radius:8px;
                        box-shadow: 0 0 60px rgba(0,0,0,.9); }}
  .modal-close {{ position:fixed; top:20px; right:28px; color:#fff; font-size:28px;
                  cursor:pointer; z-index:1001; line-height:1; }}

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
      Powered by TheChartGuys Pattern Framework · QuestDB · 1-min OHLCV
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

<!-- ── Image Modal ────────────────────────────────────────────────────────── -->
<div class="modal-overlay" id="modal" onclick="closeModal()">
  <span class="modal-close" onclick="closeModal()">✕</span>
  <img id="modal-img" src="" alt="Chart">
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

// ── Modal ─────────────────────────────────────────────────────────────────────
function openModal(img) {{
  document.getElementById('modal-img').src = img.src;
  document.getElementById('modal').classList.add('active');
}}
function closeModal() {{
  document.getElementById('modal').classList.remove('active');
}}
document.addEventListener('keydown', e => {{ if(e.key==='Escape') closeModal(); }});

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
