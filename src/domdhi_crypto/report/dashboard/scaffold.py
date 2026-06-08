_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Crypto Dashboard</title>
<style>
* {{ box-sizing: border-box; }}
body {{ margin:0; background:{bg}; color:{text};
  font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; padding:24px; }}
h1 {{ font-size:20px; margin:0 0 2px; }}
.gen {{ color:{muted}; font-size:12px; margin-bottom:20px; }}
.summary {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
  gap:14px; margin-bottom:20px; }}
.card {{ background:{card}; border:1px solid {border}; border-radius:10px; padding:16px; }}
.label {{ color:{muted}; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
.big {{ font-size:26px; font-weight:600; margin-top:6px; }}
.section-title {{ font-size:13px; color:{muted}; text-transform:uppercase;
  letter-spacing:.05em; margin:24px 0 10px; }}
.arow {{ display:flex; align-items:center; gap:10px; margin:6px 0; }}
.asym {{ width:54px; font-weight:600; font-size:13px; }}
.abar {{ flex:1; background:{bg}; border:1px solid {border}; border-radius:5px;
  height:14px; overflow:hidden; }}
.abar div {{ height:100%; }}
.apct {{ width:50px; text-align:right; color:{muted}; font-size:12px; }}
table {{ width:100%; border-collapse:collapse; }}
th {{ text-align:left; color:{muted}; font-size:11px; text-transform:uppercase;
  letter-spacing:.04em; padding:8px 10px; border-bottom:1px solid {border}; }}
td {{ padding:10px; border-bottom:1px solid {border}; font-size:13px; vertical-align:middle; }}
tr:hover td {{ background:#1c2129; }}
.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
.sym {{ font-weight:600; }}
.muted {{ color:{muted}; font-size:11px; }}
.pill {{ display:inline-block; padding:1px 7px; border-radius:10px; font-size:11px;
  font-weight:600; }}
.pill.bull {{ background:rgba(63,185,80,.15); color:{green}; }}
.pill.bear {{ background:rgba(248,81,73,.15); color:{red}; }}
.pill.stable {{ background:#21262d; color:{muted}; }}
.charts {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(420px,1fr)); gap:14px; }}
.chart {{ padding:14px 16px; }}
.chead {{ display:flex; align-items:baseline; gap:12px; margin-bottom:4px; }}
.csym {{ font-size:16px; font-weight:700; }}
.cprice {{ font-size:14px; color:{muted}; font-variant-numeric:tabular-nums; }}
.cleg {{ margin-left:auto; font-size:11px; color:{muted}; }}
.csig {{ color:{muted}; font-size:11px; margin-top:6px; }}
.panel {{ padding:14px 16px; margin-bottom:8px; }}
.panel .uchart {{ width:100%; }}
.panel table {{ margin-top:6px; }}
.figs {{ display:flex; flex-wrap:wrap; gap:24px; margin-bottom:10px; }}
.fig {{ min-width:120px; }}
.fig .label {{ font-size:11px; }}
.fig .val {{ font-size:20px; font-weight:600; margin-top:2px;
  font-variant-numeric:tabular-nums; }}
.uplot {{ font-family:inherit; }}
.sigwrap {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:12px; }}
.sigblock {{ background:{bg}; border:1px solid {border}; border-radius:8px; padding:10px 12px; }}
.sigblock .csym {{ font-size:14px; font-weight:700; margin-bottom:4px; }}
.siglist {{ margin:4px 0 6px; padding-left:18px; font-size:12px; }}
.siglist li {{ margin:2px 0; }}
table.corr {{ width:auto; }}
table.corr th, table.corr td {{ padding:5px 9px; font-size:12px; text-align:center; }}
</style>
<style>{uplot_css}</style>
</head>
<body>
<script>{uplot_js}</script>
<h1>Crypto Portfolio Dashboard</h1>
<div class="gen">Generated {gen} · source: crypto.db (CoinGecko)</div>
<div class="summary">{cards}</div>
<div class="section-title">Allocation</div>
{alloc}
<div class="section-title">Holdings</div>
<table><thead><tr><th>Asset</th><th class="num">Price</th><th class="num">Amount</th>
<th class="num">Value</th><th class="num">P/L</th><th>90d</th><th>Signal</th></tr></thead>
<tbody>{trs}</tbody></table>
<div class="section-title">Charts · 180-day price with moving averages</div>
<div class="charts">{charts}</div>
{panels}
</body></html>
"""
