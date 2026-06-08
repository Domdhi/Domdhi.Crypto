"""Generate a self-contained HTML dashboard from crypto.db.

No web server, no CDN, no JS framework — charts are inline SVG rendered in
Python, data is baked in at generation time. Open the file directly or view it
in Obsidian. Regenerate after each `ingest`.

    domdhi-crypto dashboard            # writes dashboard.html
    domdhi-crypto dashboard --open     # writes + opens in browser
"""
import json
from datetime import UTC, datetime

from domdhi_crypto.portfolio import ledger
from domdhi_crypto.shared import db, paths
from domdhi_crypto.signals import ta

from .charts import (
    _esc,
    _fmt_money,
    _fmt_pct,
    _load_vendor,
    _pl_color,
    _price_chart,
    _rsi_strip,
    _sparkline,
)
from .panels import _assemble_panels
from .scaffold import _TEMPLATE
from .theme import (
    BG,
    BLUE,
    BORDER,
    CARD,
    GOLD,
    GREEN,
    MUTED,
    PURPLE,
    RED,
    TEXT,
)


def build(open_after=False):
    coins_path = paths.coins_path()
    if not coins_path.exists():
        raise SystemExit(
            f"Missing {paths.COINS_FILE}. Copy {paths.COINS_EXAMPLE} -> {paths.COINS_FILE}."
        )
    with open(coins_path, encoding="utf-8") as f:
        cfg = json.load(f)
    conn = db.connect()

    rows = []
    total_val = total_cost = 0.0
    for c in cfg["coins"]:
        price = db.latest_snapshot_price(conn, c["id"])
        amount = c.get("amount", 0)
        if price is None:
            continue
        value = price * amount
        cost = c.get("avg_entry", 0) * amount
        pl = value - cost
        plpct = (pl / cost * 100) if cost else 0.0
        total_val += value
        total_cost += cost
        series = db.load_close_series(conn, c["id"])
        analysis = ta.analyze(series["close"]) if (series is not None and not c.get("stable")) else None
        spark = _sparkline(list(series["close"].iloc[-90:])) if series is not None else ""
        rows.append({
            "c": c, "price": price, "value": value, "pl": pl, "plpct": plpct,
            "series": series, "analysis": analysis, "spark": spark,
        })

    rows.sort(key=lambda r: r["value"], reverse=True)
    total_pl = total_val - total_cost
    total_plpct = (total_pl / total_cost * 100) if total_cost else 0.0
    gen = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    # ---- summary cards ----
    cards = "".join([
        f'<div class="card"><div class="label">Portfolio Value</div>'
        f'<div class="big">{_fmt_money(total_val)}</div></div>',
        f'<div class="card"><div class="label">Unrealized P/L</div>'
        f'<div class="big" style="color:{_pl_color(total_pl)}">{_fmt_money(total_pl)} '
        f'<span style="font-size:16px">{_fmt_pct(total_plpct)}</span></div></div>',
        f'<div class="card"><div class="label">Cost Basis</div>'
        f'<div class="big">{_fmt_money(total_cost)}</div></div>',
        f'<div class="card"><div class="label">Positions</div>'
        f'<div class="big">{len(rows)}</div></div>',
    ])

    # ---- allocation bars ----
    alloc = ""
    palette = [BLUE, GOLD, PURPLE, GREEN, "#db61a2", "#f0883e", "#56d4dd", MUTED]
    for i, r in enumerate(rows):
        pct = (r["value"] / total_val * 100) if total_val else 0
        col = palette[i % len(palette)]
        alloc += (f'<div class="arow"><span class="asym">{_esc(r["c"]["symbol"])}</span>'
                  f'<div class="abar"><div style="width:{pct:.1f}%;background:{col}"></div></div>'
                  f'<span class="apct">{pct:.1f}%</span></div>')

    # ---- holdings table ----
    trs = ""
    for r in rows:
        a = r["analysis"]
        if a:
            rsi_v = a.get("rsi")
            regime = "bull" if (a.get("sma200") and r["price"] > a["sma200"]) else "bear"
            macd_tag = "+" if (a.get("macd_hist") or 0) > 0 else "−"
            sig = (f'<span class="pill {regime}">{regime}</span> '
                   f'RSI {rsi_v:.0f} · MACD{macd_tag}' if rsi_v is not None else regime)
        else:
            sig = '<span class="pill stable">stable</span>'
        trs += (
            f'<tr><td class="sym">{_esc(r["c"]["symbol"])}</td>'
            f'<td class="num">{_fmt_money(r["price"], 4)}</td>'
            f'<td class="num">{r["c"].get("amount", 0):,.4f}</td>'
            f'<td class="num">{_fmt_money(r["value"])}</td>'
            f'<td class="num" style="color:{_pl_color(r["pl"])}">{_fmt_money(r["pl"])}<br>'
            f'<span class="muted">{_fmt_pct(r["plpct"])}</span></td>'
            f'<td>{r["spark"]}</td><td class="sig">{sig}</td></tr>'
        )

    # ---- per-coin charts ----
    charts = ""
    for r in rows:
        if r["series"] is None or r["c"].get("stable"):
            continue
        a = r["analysis"]
        legend = (f'<span style="color:{TEXT}">● price</span> '
                  f'<span style="color:{BLUE}">● SMA20</span> '
                  f'<span style="color:{GOLD}">● SMA50</span> '
                  f'<span style="color:{PURPLE}">● SMA200</span>')
        sigs = _esc(" · ".join(a["signals"])) if a else ""
        charts += (
            f'<div class="chart card"><div class="chead">'
            f'<span class="csym">{_esc(r["c"]["symbol"])}</span>'
            f'<span class="cprice">{_fmt_money(r["price"], 4)}</span>'
            f'<span class="cleg">{legend}</span></div>'
            f'{_price_chart(r["series"])}{_rsi_strip(r["series"])}'
            f'<div class="csig">{sigs}</div></div>'
        )

    # ---- decision panels (E18-S1 seam; S2-S5 register _panel_* fns) ----
    # Assembled while ``conn`` is still open — panels read live data through it.
    # NAV is computed once here and shared via ctx (used by both NAV and risk panels).
    ctx = {"conn": conn, "coins_cfg": cfg, "rows": rows,
           "nav": ledger.nav_series(conn, cfg)}
    panels = _assemble_panels(ctx)

    conn.close()

    page = _TEMPLATE.format(
        gen=gen, cards=cards, alloc=alloc, trs=trs, charts=charts,
        panels=panels, uplot_js=_load_vendor("uplot.min.js"),
        uplot_css=_load_vendor("uplot.min.css"),
        bg=BG, card=CARD, border=BORDER, text=TEXT, muted=MUTED,
        green=GREEN, red=RED,
    )
    out_path = paths.dashboard_path()
    out_path.write_text(page, encoding="utf-8")
    if open_after:
        import webbrowser
        webbrowser.open(out_path.as_uri())
    return out_path
