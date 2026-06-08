#!/usr/bin/env python3
"""Crypto data + technical-analysis CLI backed by CoinGecko + SQLite.

    domdhi-crypto init                 # create the SQLite db
    domdhi-crypto ingest [--days 365]  # pull snapshot + history for all coins
    domdhi-crypto ta BTC               # indicators + signals for one coin
    domdhi-crypto report               # live portfolio value + P/L + signals
    domdhi-crypto dashboard [--open]   # build the offline HTML dashboard
    domdhi-crypto digest [--out PATH]  # write a Markdown brief of triggered signals
    domdhi-crypto factors BTC          # rank built-in factors by IC/ICIR
    domdhi-crypto backtest BTC         # look-ahead-safe backtest of one factor rule
    domdhi-crypto arena BTC            # cortex vs buy-and-hold + a rule baseline
    domdhi-crypto walkforward BTC      # out-of-sample sub-period (fold) validation
    domdhi-crypto mcp                  # run the MCP server for an LLM agent (needs [mcp] extra)

Coins, holdings, and avg-entry prices live in coins.local.json. The API key lives in
config.local.json (gitignored). Both, plus crypto.db and dashboard.html, are
resolved from the data directory ($DOMDHI_CRYPTO_HOME or the current directory).
"""
import argparse
import json
import math
from datetime import UTC, datetime
from importlib.metadata import version as pkg_version

from domdhi_crypto.backtest import arena, attribution, engine, walkforward
from domdhi_crypto.ingest import prices_provider
from domdhi_crypto.report import dashboard, digest
from domdhi_crypto.shared import db, paths
from domdhi_crypto.signals import effectiveness, factors, ta


def _version():
    """Return the installed package version (single source: package metadata)."""
    return pkg_version("domdhi-crypto")


def load_coins():
    coins_path = paths.coins_path()
    if not coins_path.exists():
        raise SystemExit(
            f"Missing {paths.COINS_FILE}. Copy {paths.COINS_EXAMPLE} -> {paths.COINS_FILE} "
            f"and set your own holdings."
        )
    with open(coins_path, encoding="utf-8") as f:
        return json.load(f)


def fmt(x, d=4):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    return f"{x:,.{d}f}" if isinstance(x, (int, float)) else "n/a"


def _daily_rows(chart):
    """Collapse market_chart arrays into one row per UTC date (last point wins)."""
    vols = {int(ts): v for ts, v in chart.get("total_volumes", [])}
    mcaps = {int(ts): v for ts, v in chart.get("market_caps", [])}
    by_date = {}
    for ts, price in chart.get("prices", []):
        ts = int(ts)
        date = datetime.fromtimestamp(ts / 1000, tz=UTC).strftime("%Y-%m-%d")
        by_date[date] = (date, price, vols.get(ts), mcaps.get(ts))
    return list(by_date.values())


def cmd_init(args):
    print(f"Initialized {db.init_db()}")


def cmd_ingest(args):
    cfg = load_coins()
    coins = cfg["coins"]
    vs = cfg.get("vs_currency", "usd")
    cg: prices_provider.PricesProvider = prices_provider.get_provider()
    db.init_db()
    conn = db.connect()
    fetched_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    ids = [c["id"] for c in coins]
    print(f"Snapshot for {len(ids)} coins...")
    by_id = {m["id"]: m for m in cg.markets(ids, vs=vs)}
    for c in coins:
        m = by_id.get(c["id"])
        if not m:
            print(f"  ! no market data for {c['id']}")
            continue
        db.upsert_coin(conn, c["id"], (m.get("symbol") or c["symbol"]).upper(),
                       m.get("name", c["id"]))
        db.insert_snapshot(
            conn, c["id"], fetched_at, m.get("current_price"), m.get("market_cap"),
            m.get("price_change_percentage_24h_in_currency"),
            m.get("price_change_percentage_7d_in_currency"),
            m.get("price_change_percentage_30d_in_currency"),
        )
    conn.commit()

    for c in coins:
        if c.get("stable"):
            continue
        print(f"History for {c['symbol']} ({c['id']})...")
        try:
            rows = _daily_rows(cg.market_chart(c["id"], days=args.days, vs=vs))
            db.upsert_prices(conn, c["id"], rows)
            print(f"  {len(rows)} daily price rows")
        except Exception as e:
            print(f"  ! price fetch failed: {e}")
        try:
            candles = [(int(t), o, h, lo, cl)
                       for t, o, h, lo, cl in cg.ohlc(c["id"], days=min(args.days, 365), vs=vs)]
            db.upsert_ohlc(conn, c["id"], candles)
            print(f"  {len(candles)} OHLC candles")
        except Exception as e:
            print(f"  ! ohlc fetch failed: {e}")
        conn.commit()
    conn.close()
    print("Ingest complete.")


def _resolve(coins, token):
    token = token.lower()
    for c in coins:
        if token in (c["id"].lower(), c["symbol"].lower()):
            return c
    return None


def cmd_ta(args):
    cfg = load_coins()
    c = _resolve(cfg["coins"], args.symbol)
    if not c:
        raise SystemExit(f"Unknown coin '{args.symbol}'. Check coins.local.json.")
    if c.get("stable"):
        raise SystemExit(
            f"{c['symbol']} is flagged as a stablecoin, so no history is ingested "
            f"and TA is skipped. Remove \"stable\": true in coins.local.json to analyze it."
        )
    conn = db.connect()
    series = db.load_close_series(conn, c["id"])
    conn.close()
    if series is None:
        raise SystemExit(
            f"No price data for {c['symbol']} yet. Run: domdhi-crypto ingest"
        )
    r = ta.analyze(series["close"])
    print(f"\n{c['symbol']} - {c['id']}  ({r['n_days']} days of data)")
    print("=" * 48)
    print(f"  Price          ${fmt(r['price'])}")
    print(f"  RSI(14)        {fmt(r['rsi'], 1)}")
    print(f"  MACD hist      {fmt(r['macd_hist'], 4)}")
    print(f"  SMA 20/50/200  {fmt(r['sma20'])} / {fmt(r['sma50'])} / {fmt(r['sma200'])}")
    print(f"  Bollinger %B   {fmt(r['bb_pctb'], 2)}")
    if r["volatility_annual"] is not None:
        print(f"  Volatility     {r['volatility_annual'] * 100:.0f}% annualized")
    print("  Signals:")
    for s in r["signals"]:
        print(f"    - {s}")
    print()


def cmd_report(args):
    cfg = load_coins()
    conn = db.connect()
    print(f"\nPortfolio Report  ({datetime.now(UTC):%Y-%m-%d %H:%MZ})")
    print("=" * 78)
    print(f"{'SYM':<6}{'Price':>13}{'Value':>13}{'P/L $':>13}{'P/L %':>9}  Signal")
    print("-" * 78)
    total_val = total_cost = 0.0
    for c in cfg["coins"]:
        price = db.latest_snapshot_price(conn, c["id"])
        amount = c.get("amount", 0)
        if price is None:
            print(f"{c['symbol']:<6}{'n/a':>13}")
            continue
        value = price * amount
        cost = c.get("avg_entry", 0) * amount
        pl = value - cost
        plpct = (pl / cost * 100) if cost else 0.0
        total_val += value
        total_cost += cost
        signal = "stablecoin"
        if not c.get("stable"):
            series = db.load_close_series(conn, c["id"])
            if series is not None:
                r = ta.analyze(series["close"])
                regime = "bull" if (r.get("sma200") and price > r["sma200"]) else "bear"
                macd_tag = "MACD+" if (r.get("macd_hist") or 0) > 0 else "MACD-"
                rsi_tag = f"RSI{r['rsi']:.0f}" if r.get("rsi") is not None else "RSI-"
                signal = f"{rsi_tag} {regime} {macd_tag}"
        print(f"{c['symbol']:<6}{price:>13,.4f}{value:>13,.2f}{pl:>+13,.2f}{plpct:>+8.1f}%  {signal}")
    conn.close()
    print("-" * 78)
    tpl = total_val - total_cost
    tplpct = (tpl / total_cost * 100) if total_cost else 0.0
    print(f"{'TOTAL':<6}{'':>13}{total_val:>13,.2f}{tpl:>+13,.2f}{tplpct:>+8.1f}%")
    print()


def cmd_dashboard(args):
    path = dashboard.build(open_after=args.open)
    print(f"Wrote {path}")


def cmd_digest(args):
    path = digest.build(out_path=args.out)
    print(f"Wrote {path}")


def cmd_mcp(args):
    """Launch the MCP server so an LLM agent can reason over the local portfolio.

    The server lives behind the optional ``[mcp]`` extra (the core package stays
    3-dep, ADR-001). If the extra isn't installed, ``mcp_server.run`` raises
    ``ImportError`` (its lazy ``from mcp...`` import); convert that into an
    actionable ``SystemExit`` rather than a traceback.
    """
    try:
        from domdhi_crypto_mcp import server as mcp_server
        mcp_server.run()
    except ImportError as exc:
        raise SystemExit(
            "The MCP server requires the optional 'mcp' extra. "
            "Install it with: pip install domdhi-crypto[mcp]"
        ) from exc


def _load_series_or_exit(symbol, *, ohlc=False):
    """Resolve a coin, reject stablecoins, and load its price frame — or ``SystemExit``
    with an actionable message. Shared by the ``factors`` and ``backtest`` commands.

    Stablecoins are rejected up front (mirroring ``cmd_ta``): they have no ingested
    history, so the generic "Run: ingest" message would be a dead-end loop because
    ``ingest`` skips stables. Warns (does not fail) when the series is too short to
    analyze meaningfully. Returns ``(coin_dict, series_frame)``.

    When ``ohlc`` is True the frame comes from ``db.load_ohlcv_daily`` (full
    open/high/low/close/volume), which the high/low factors (ATR/WILLR/CCI/AROON/
    ADX) require; otherwise from ``db.load_close_series`` (close+volume).
    """
    cfg = load_coins()
    c = _resolve(cfg["coins"], symbol)
    if not c:
        raise SystemExit(f"Unknown coin '{symbol}'. Check coins.local.json.")
    if c.get("stable"):
        raise SystemExit(
            f"{c['symbol']} is flagged as a stablecoin, so no history is ingested. "
            'Remove "stable": true in coins.local.json to analyze it.'
        )
    conn = db.connect()
    series = db.load_ohlcv_daily(conn, c["id"]) if ohlc else db.load_close_series(conn, c["id"])
    conn.close()
    if series is None:
        kind = "OHLC candle" if ohlc else "price"
        raise SystemExit(f"No {kind} data for {c['symbol']} yet. Run: domdhi-crypto ingest")
    if len(series) < 30:
        print(
            f"  ! only {len(series)} days of data for {c['symbol']} — "
            "results may be unreliable."
        )
    return c, series


def cmd_factors(args):
    if args.horizon < 1:
        raise SystemExit("--horizon must be >= 1.")
    if args.top is not None and args.top < 1:
        raise SystemExit("--top must be >= 1.")
    c, series = _load_series_or_exit(args.symbol, ohlc=args.ohlc)
    scored = effectiveness.score_factors(series, factors.BUILTIN_FACTORS, horizon=args.horizon)
    if args.top is not None:
        scored = scored[: args.top]
    print(f"\n{c['symbol']} factor effectiveness (horizon={args.horizon})")
    print(f"{'FACTOR':<26}{'CATEGORY':<14}{'IC':>10}{'ICIR':>10}")
    print("-" * 60)
    for row in scored:
        print(
            f"{row['name']:<26}{(row.get('category') or ''):<14}"
            f"{fmt(row['ic'], 4):>10}{fmt(row['icir'], 4):>10}"
        )
    print()


def cmd_backtest(args):
    if args.cash <= 0:
        raise SystemExit("--cash must be > 0.")
    if args.slippage_bps < 0 or args.fee_rate < 0:
        raise SystemExit("--slippage-bps and --fee-rate must be >= 0.")
    expr_by_name = {f["name"]: f["expression"] for f in factors.BUILTIN_FACTORS}
    if args.factor not in expr_by_name:
        raise SystemExit(
            f"Unknown factor '{args.factor}'. Run: domdhi-crypto factors {args.symbol} "
            "to list the available factor names."
        )
    c, series = _load_series_or_exit(args.symbol, ohlc=args.ohlc)

    rule = engine.SignalRule(
        factor_name=args.factor,
        expression=expr_by_name[args.factor],
        entry_threshold=args.entry,
        exit_threshold=args.exit,
    )
    result = engine.run_backtest(
        series,
        [rule],
        initial_cash=args.cash,
        slippage_bps=args.slippage_bps,
        fee_rate=args.fee_rate,
    )
    s = result.summary
    print(
        f"\n{c['symbol']} backtest — factor={args.factor} "
        f"enter>{fmt(args.entry, 4)} exit<{fmt(args.exit, 4)}  "
        f"(slip={fmt(args.slippage_bps, 1)}bps fee={fmt(args.fee_rate, 4)})"
    )
    print("=" * 60)
    print(f"  Total return        {fmt(s['total_return'] * 100, 2)}%")
    print(f"  Realized return     {fmt(s['total_realized_return'] * 100, 2)}%")
    print(f"  Win rate            {fmt(s['win_rate'] * 100, 1)}%")
    print(f"  Max drawdown        {fmt(s['max_drawdown'] * 100, 2)}%")
    print(f"  Trades              {len(result.trades)}")

    attr = attribution.attribute_by_factor(result)
    if attr:
        print("\n  By factor:")
        print(f"  {'FACTOR':<26}{'TRADES':>8}{'TOTAL%':>10}{'MEAN%':>10}{'WIN%':>8}")
        print("  " + "-" * 60)
        for name, st in attr.items():
            print(
                f"  {name:<26}{st['n_trades']:>8}"
                f"{fmt(st['total_return'] * 100, 2):>10}"
                f"{fmt(st['mean_return'] * 100, 2):>10}"
                f"{fmt(st['win_rate'] * 100, 1):>8}"
            )
    print()


def _build_cortex_rules(factor_arg, expr_by_name, entry, exit_, symbol):
    """Parse a comma-separated ``--factor`` value into an ordered list of cortex
    ``SignalRule`` objects.

    Precedence is FIRST-RULE-WINS, not a weighted blend: ``engine.run_backtest``
    opens a position on the first rule (in list order) whose signal fires and
    exits on the rule that opened the trade (see engine.py Step 4). So
    ``--factor a,b`` means "enter on a if it fires, else b" — a deterministic
    priority cascade, NOT a combined/voting signal. All rules share the same
    ``entry``/``exit`` thresholds.
    """
    names = [n.strip() for n in factor_arg.split(",") if n.strip()]
    if not names:
        raise SystemExit("--factor must name at least one factor.")
    rules = []
    for name in names:
        if name not in expr_by_name:
            raise SystemExit(
                f"Unknown factor '{name}' for --factor. Run: domdhi-crypto factors {symbol} "
                "to list the available factor names."
            )
        rules.append(
            engine.SignalRule(
                factor_name=name,
                expression=expr_by_name[name],
                entry_threshold=entry,
                exit_threshold=exit_,
            )
        )
    return rules


def cmd_arena(args):
    if args.cash <= 0:
        raise SystemExit("--cash must be > 0.")
    if args.slippage_bps < 0 or args.fee_rate < 0:
        raise SystemExit("--slippage-bps and --fee-rate must be >= 0.")
    expr_by_name = {f["name"]: f["expression"] for f in factors.BUILTIN_FACTORS}
    cortex_rules = _build_cortex_rules(
        args.factor, expr_by_name, args.entry, args.exit, args.symbol
    )
    if args.baseline_factor not in expr_by_name:
        raise SystemExit(
            f"Unknown factor '{args.baseline_factor}' for --baseline-factor. "
            f"Run: domdhi-crypto factors {args.symbol} to list the available factor names."
        )
    c, series = _load_series_or_exit(args.symbol)

    # The rule baseline is a trend-follow: in while the factor is positive, out below 0.
    baseline_rule = engine.SignalRule(
        factor_name=args.baseline_factor,
        expression=expr_by_name[args.baseline_factor],
        entry_threshold=0.0,
        exit_threshold=0.0,
    )
    result = arena.run_arena(
        series,
        cortex_rules=cortex_rules,
        baseline_rules=[baseline_rule],
        initial_cash=args.cash,
        slippage_bps=args.slippage_bps,
        fee_rate=args.fee_rate,
    )

    print(
        f"\n{c['symbol']} arena — cortex factor={args.factor} "
        f"enter>{fmt(args.entry, 4)} exit<{fmt(args.exit, 4)}  "
        f"(slip={fmt(args.slippage_bps, 1)}bps fee={fmt(args.fee_rate, 4)})"
    )
    print("=" * 60)
    print(f"  {'STRATEGY':<22}{'TOTAL%':>10}{'vs CORTEX%':>14}")
    print("  " + "-" * 46)
    cortex_tr = result.cortex.summary["total_return"]
    print(f"  {result.cortex.name:<22}{fmt(cortex_tr * 100, 2):>10}{'—':>14}")
    for b in result.baselines:
        rel = result.relative[b.name]
        print(
            f"  {b.name:<22}{fmt(b.summary['total_return'] * 100, 2):>10}"
            f"{fmt(rel * 100, 2):>14}"
        )
    print("\n  (vs cortex = cortex total return − baseline total return)")

    print("\n  By factor (cortex):")
    attr = result.attribution
    if attr:
        print(f"  {'FACTOR':<26}{'TRADES':>8}{'TOTAL%':>10}{'MEAN%':>10}{'WIN%':>8}")
        print("  " + "-" * 62)
        for name, st in attr.items():
            print(
                f"  {name:<26}{st['n_trades']:>8}"
                f"{fmt(st['total_return'] * 100, 2):>10}"
                f"{fmt(st['mean_return'] * 100, 2):>10}"
                f"{fmt(st['win_rate'] * 100, 1):>8}"
            )
    else:
        print("    (no cortex trades to attribute)")
    print()


def cmd_walkforward(args):
    if args.folds < 1:
        raise SystemExit("--folds must be >= 1.")
    if args.cash <= 0:
        raise SystemExit("--cash must be > 0.")
    if args.slippage_bps < 0 or args.fee_rate < 0:
        raise SystemExit("--slippage-bps and --fee-rate must be >= 0.")
    expr_by_name = {f["name"]: f["expression"] for f in factors.BUILTIN_FACTORS}
    cortex_rules = _build_cortex_rules(
        args.factor, expr_by_name, args.entry, args.exit, args.symbol
    )
    c, series = _load_series_or_exit(args.symbol)
    if args.folds > len(series):
        raise SystemExit(
            f"--folds ({args.folds}) cannot exceed the {len(series)} available bars "
            f"for {c['symbol']}. Ingest more history or request fewer folds."
        )

    result = walkforward.walk_forward(
        series,
        cortex_rules,
        n_splits=args.folds,
        initial_cash=args.cash,
        slippage_bps=args.slippage_bps,
        fee_rate=args.fee_rate,
    )

    print(
        f"\n{c['symbol']} walk-forward — cortex factor={args.factor} "
        f"enter>{fmt(args.entry, 4)} exit<{fmt(args.exit, 4)}  "
        f"({result.n_folds} folds, slip={fmt(args.slippage_bps, 1)}bps fee={fmt(args.fee_rate, 4)})"
    )
    print(
        "  Out-of-sample sub-period segmentation of ONE full-frame backtest "
        "(no per-fold refit)."
    )
    print("=" * 78)
    print(
        f"  {'FOLD':<5}{'START':<12}{'END':<12}"
        f"{'CORTEX%':>10}{'BENCH%':>10}{'EDGE%':>10}{'TRADES':>8}"
    )
    print("  " + "-" * 64)
    for fold in result.folds:
        print(
            f"  {fold.index:<5}{fold.start:%Y-%m-%d}  {fold.end:%Y-%m-%d}"
            f"{fmt(fold.cortex_return * 100, 2):>10}"
            f"{fmt(fold.benchmark_return * 100, 2):>10}"
            f"{fmt(fold.edge * 100, 2):>10}{fold.n_trades:>8}"
        )
    print("  " + "-" * 64)
    print(f"  Cortex win rate (folds with edge>0)   {fmt(result.cortex_win_rate * 100, 1)}%")
    print(f"  Mean edge                             {fmt(result.mean_edge * 100, 2)}%")
    print(f"  Mean cortex return                    {fmt(result.mean_cortex_return * 100, 2)}%")
    print(f"  Mean benchmark return                 {fmt(result.mean_benchmark_return * 100, 2)}%")
    print()


def main():
    p = argparse.ArgumentParser(description="Crypto TA via CoinGecko + SQLite")
    p.add_argument("--version", action="version", version=f"%(prog)s {_version()}")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(func=cmd_init)
    pi = sub.add_parser("ingest")
    pi.add_argument("--days", type=int, default=365)
    pi.set_defaults(func=cmd_ingest)
    pt = sub.add_parser("ta")
    pt.add_argument("symbol")
    pt.set_defaults(func=cmd_ta)
    sub.add_parser("report").set_defaults(func=cmd_report)
    pf = sub.add_parser("factors")
    pf.add_argument("symbol")
    pf.add_argument("--horizon", type=int, default=5)
    pf.add_argument("--top", type=int, default=None)
    pf.add_argument(
        "--ohlc",
        action="store_true",
        help="score against the daily OHLCV frame (enables high/low factors: "
        "ATR/Williams %%R/CCI/Aroon/ADX)",
    )
    pf.set_defaults(func=cmd_factors)
    pb = sub.add_parser("backtest")
    pb.add_argument("symbol")
    pb.add_argument("--factor", default="price_vs_sma20")
    pb.add_argument("--entry", type=float, default=0.0)
    pb.add_argument("--exit", type=float, default=0.0)
    pb.add_argument("--cash", type=float, default=10000.0)
    pb.add_argument("--slippage-bps", type=float, default=0.0)
    pb.add_argument("--fee-rate", type=float, default=0.0)
    pb.add_argument(
        "--ohlc",
        action="store_true",
        help="backtest against the daily OHLCV frame (enables high/low factors)",
    )
    pb.set_defaults(func=cmd_backtest)
    pa = sub.add_parser("arena", help="paper-trade the cortex vs buy-and-hold + a rule baseline")
    pa.add_argument("symbol")
    pa.add_argument(
        "--factor",
        default="rsi_centered",
        help="cortex factor(s), comma-separated for a first-rule-wins cascade "
        "(default: rsi_centered)",
    )
    pa.add_argument("--entry", type=float, default=0.0)
    pa.add_argument("--exit", type=float, default=0.0)
    pa.add_argument(
        "--baseline-factor",
        default="price_vs_sma50",
        help="rule-baseline factor (default: price_vs_sma50)",
    )
    pa.add_argument("--cash", type=float, default=10000.0)
    pa.add_argument("--slippage-bps", type=float, default=0.0)
    pa.add_argument("--fee-rate", type=float, default=0.0)
    pa.set_defaults(func=cmd_arena)
    pw = sub.add_parser(
        "walkforward",
        help="out-of-sample sub-period (fold) validation of the cortex strategy",
    )
    pw.add_argument("symbol")
    pw.add_argument(
        "--factor",
        default="rsi_centered",
        help="cortex factor(s), comma-separated for a first-rule-wins cascade "
        "(default: rsi_centered)",
    )
    pw.add_argument("--entry", type=float, default=0.0)
    pw.add_argument("--exit", type=float, default=0.0)
    pw.add_argument("--folds", type=int, default=4, help="number of contiguous folds (default: 4)")
    pw.add_argument("--cash", type=float, default=10000.0)
    pw.add_argument("--slippage-bps", type=float, default=0.0)
    pw.add_argument("--fee-rate", type=float, default=0.0)
    pw.set_defaults(func=cmd_walkforward)
    pd = sub.add_parser("dashboard")
    pd.add_argument("--open", action="store_true", help="open in browser after writing")
    pd.set_defaults(func=cmd_dashboard)
    pdg = sub.add_parser("digest", help="write a Markdown brief of triggered signals")
    pdg.add_argument("--out", default=None, help="override output path (default: digest.md in the data dir)")
    pdg.set_defaults(func=cmd_digest)
    sub.add_parser("mcp", help="run the MCP server (needs the [mcp] extra)").set_defaults(func=cmd_mcp)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
