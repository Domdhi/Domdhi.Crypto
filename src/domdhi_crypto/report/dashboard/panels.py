import logging

from domdhi_crypto.agent import context
from domdhi_crypto.backtest import attribution, engine
from domdhi_crypto.portfolio import ledger, risk
from domdhi_crypto.signals import factors

from .charts import (
    _esc,
    _fig,
    _finite,
    _fmt_money,
    _num_or_na,
    _panel,
    _pct_or_na,
    _pl_color,
    _series_xy,
    _uplot_chart,
)
from .theme import BLUE, GOLD, GREEN, MUTED, RED

_log = logging.getLogger(__name__)


def _corr_color(v):
    """Tint a correlation cell: warmer (red) the higher the positive correlation."""
    a = max(0.0, min(1.0, (v + 1.0) / 2.0))
    return f"rgba(248,81,73,{a * 0.35:.2f})"


def _corr_table(corr):
    """Render a correlation DataFrame as a tinted HTML table. ``""`` when empty;
    NaN cells render as ``"n/a"`` (never a fabricated number)."""
    if corr is None or getattr(corr, "empty", True):
        return ""
    syms = list(corr.columns)
    head = "".join(f"<th>{_esc(s)}</th>" for s in syms)
    body = ""
    for r in syms:
        cells = ""
        for c in syms:
            v = corr.loc[r, c]
            if _finite(v):
                cells += (f'<td class="num" style="background:{_corr_color(float(v))}">'
                          f'{float(v):.2f}</td>')
            else:
                cells += '<td class="num">n/a</td>'
        cells_row = f'<tr><td class="sym">{_esc(r)}</td>{cells}</tr>'
        body += cells_row
    return (f'<table class="corr"><thead><tr><th></th>{head}</tr></thead>'
            f'<tbody>{body}</tbody></table>')


def _panel_proof(ctx):
    """S1 proof: an interactive uPlot price line for the largest holding.

    Demonstrates the vendored substrate renders offline. Real decision panels
    (NAV/risk/signals/backtest) are added by S2-S5."""
    rows = [r for r in ctx["rows"] if r["series"] is not None and not r["c"].get("stable")]
    if not rows:
        return ""
    r = rows[0]  # rows are value-sorted desc; largest holding
    xs, ys = _series_xy(r["series"]["close"].iloc[-180:])
    if xs is None:
        return ""
    sym = _esc(r["c"]["symbol"])
    chart = _uplot_chart("proof-chart", xs,
                         [{"name": f"{sym} price", "data": ys, "color": BLUE}])
    return _panel(f"Interactive price · {sym} (uPlot)", chart)


def _panel_nav(ctx):
    """E18-S2: NAV-over-time uPlot line + realized/unrealized P/L figures.

    Sources are the pure ``ledger`` functions (conn + coins_cfg injected). NAV
    chart is omitted when there is no plottable series; P/L figures are always
    finite (the ledger finite-guards every float), so they render as money rather
    than crashing when there are no transactions."""
    conn, cfg = ctx["conn"], ctx["coins_cfg"]
    nav = ctx.get("nav")
    realized = ledger.realized_pl(conn, cfg)
    unrealized = ledger.unrealized_pl(conn, cfg)

    figs = (_fig("Realized P/L", _fmt_money(realized), _pl_color(realized))
            + _fig("Unrealized P/L", _fmt_money(unrealized), _pl_color(unrealized)))
    xs, ys = _series_xy(nav)
    chart = ""
    if xs is not None:
        chart = _uplot_chart("nav-chart", xs,
                             [{"name": "NAV", "data": ys, "color": GREEN}])
    return _panel("Portfolio · NAV &amp; P/L", f'<div class="figs">{figs}</div>{chart}')


def _panel_risk(ctx):
    """E18-S3: correlation matrix + portfolio vol + beta-to-BTC + max-drawdown.

    Every figure is finite-guarded (``risk.py`` returns float NaN under window),
    so NaN surfaces as ``"n/a"`` rather than a fabricated number or a crash. The
    correlation table is omitted entirely when fewer than two coins have history."""
    conn, cfg = ctx["conn"], ctx["coins_cfg"]
    vol = risk.portfolio_vol(conn, cfg)
    betas = risk.beta_to_btc(conn, cfg)
    nav = ctx.get("nav")
    mdd = risk.max_drawdown(nav) if (nav is not None and len(nav) >= 2) else float("nan")
    corr = risk.correlation_matrix(conn, cfg)

    figs = (_fig("Portfolio Vol (ann.)", _pct_or_na(vol, signed=False))
            + _fig("Max Drawdown", _pct_or_na(mdd),
                   RED if (_finite(mdd) and mdd < 0) else MUTED))
    for sym, b in betas.items():
        figs += _fig(f"β {_esc(sym)}", _num_or_na(b))

    body = f'<div class="figs">{figs}</div>{_corr_table(corr)}'
    return _panel("Risk", body)


# Curated decision-relevant factors surfaced under each triggered coin (mirrors
# digest._KEY_FACTORS — same source, kept local to avoid importing a private API).
_KEY_FACTORS = ("rsi_14", "macd_hist", "price_vs_sma20", "roc_10", "bb_pctb_20")


def _is_triggered(signals):
    """A coin triggers when any signal string is non-neutral (mirrors
    digest._is_triggered — only the RSI line is ever 'neutral')."""
    return any("neutral" not in s.lower() for s in signals)


def _panel_signals(ctx):
    """E18-S4: per-coin currently-triggered signals (the agent's "why now"),
    each with a few key factor values. Coins with no data / errors are skipped;
    when nothing is triggered the panel is omitted entirely."""
    conn, cfg = ctx["conn"], ctx["coins_cfg"]
    blocks = []
    for c in cfg.get("coins", []):
        result = context.build_context(c["symbol"], conn=conn, coins_cfg=cfg)
        if "error" in result:
            continue
        ta_block = result.get("signals", {}).get("ta")
        signals = ta_block.get("signals", []) if ta_block else []
        if not signals or not _is_triggered(signals):
            continue
        fv = result["signals"].get("factor_values", {})
        sig_items = "".join(f"<li>{_esc(s)}</li>" for s in signals)
        facts = [f"{_esc(name)}={float(fv[name]):.2f}"
                 for name in _KEY_FACTORS if _finite(fv.get(name))]
        facts_html = f'<div class="muted">{" · ".join(facts)}</div>' if facts else ""
        blocks.append(f'<div class="sigblock"><div class="csym">{_esc(result["symbol"])}</div>'
                      f'<ul class="siglist">{sig_items}</ul>{facts_html}</div>')
    if not blocks:
        return ""
    return _panel("Triggered Signals", f'<div class="sigwrap">{"".join(blocks)}</div>')


_BACKTEST_FACTOR = "price_vs_sma20"  # default rule (mirrors cli backtest default)


def _panel_backtest(ctx):
    """E18-S5: a cheap default-rule (`price_vs_sma20` > 0) backtest per non-stable
    coin — its equity curve as an interactive uPlot line + per-factor attribution
    table. Reading a cached run isn't possible (none is persisted), so the panel
    runs a deterministic single-rule backtest per coin; absent any priced coin the
    panel is omitted entirely (no forced run, no error)."""
    rows = [r for r in ctx["rows"]
            if r["series"] is not None and not r["c"].get("stable")]
    if not rows:
        return ""
    expr = {f["name"]: f["expression"] for f in factors.BUILTIN_FACTORS}.get(_BACKTEST_FACTOR)
    if expr is None:
        return ""
    rule = engine.SignalRule(_BACKTEST_FACTOR, expr, entry_threshold=0.0, exit_threshold=0.0)

    charts = []
    attr_rows = ""
    for r in rows:
        sym = r["c"]["symbol"]
        try:
            result = engine.run_backtest(r["series"], [rule])
        except Exception:
            _log.warning("backtest failed for %s; skipping its panel entry", sym,
                         exc_info=True)
            continue
        xs, ys = _series_xy(result.equity_curve)
        if xs is None:
            continue
        charts.append(
            f'<div class="muted">{_esc(sym)} · rule {_BACKTEST_FACTOR} &gt; 0</div>'
            # div id keys off the coin id (unique), NOT the symbol — two coins can
            # share a ticker, which would collide the id and drop one chart.
            + _uplot_chart(f"bt-{r['c']['id']}", xs,
                           [{"name": f"{sym} equity", "data": ys, "color": GOLD}]))
        for fac, d in attribution.attribute_by_factor(result).items():
            attr_rows += (f'<tr><td class="sym">{_esc(sym)}</td><td>{_esc(fac)}</td>'
                          f'<td class="num">{d["n_trades"]}</td>'
                          f'<td class="num">{_pct_or_na(d["total_return"])}</td>'
                          f'<td class="num">{_pct_or_na(d["mean_return"])}</td>'
                          f'<td class="num">{_pct_or_na(d["win_rate"], signed=False)}</td></tr>')
    if not charts:
        return ""
    table = ""
    if attr_rows:
        table = ('<table class="attr"><thead><tr><th>Coin</th><th>Factor</th>'
                 '<th class="num">Trades</th><th class="num">Total</th>'
                 '<th class="num">Mean</th><th class="num">Win%</th></tr></thead>'
                 f'<tbody>{attr_rows}</tbody></table>')
    return _panel("Backtest · equity curve &amp; attribution", "".join(charts) + table)


_PANEL_FUNCS = [_panel_proof, _panel_nav, _panel_risk, _panel_signals, _panel_backtest]


def _assemble_panels(ctx):
    """Run every registered panel; concatenate non-empty fragments. A panel that
    raises is skipped (logged-as-omitted) so it can't break the dashboard."""
    parts = []
    for fn in _PANEL_FUNCS:
        try:
            fragment = fn(ctx)
        except Exception:
            # Resilience: one broken panel must never blank the whole dashboard.
            # But the swallow is AUDIBLE — log it so a silently-omitted panel is
            # visible in normal runs (a NameError once hid here behind a green page).
            _log.warning("dashboard panel %s failed; omitting it",
                         getattr(fn, "__name__", fn), exc_info=True)
            fragment = ""
        if fragment:
            parts.append(fragment)
    return "\n".join(parts)
