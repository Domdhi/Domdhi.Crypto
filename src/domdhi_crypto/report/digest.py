"""Offline Markdown digest of triggered TA signals (Epic 15).

Filters the configured coins down to those with a *triggered* (non-neutral)
technical signal and renders a locally-composed Markdown brief — triggered
signal strings, position P/L, and a handful of factor values as rationale prose
— to ``data_dir()/digest.md``. Fully offline: no server, no push, no live LLM
call (FR-24, NFR-C2-3). ``/schedule`` can run ``domdhi-crypto digest`` to drop a
daily brief into the user's vault.

Triggered definition (v1): a coin triggers iff its
``context.build_context(...)["signals"]["ta"]["signals"]`` list contains at least
one non-neutral string. The thresholds are the defaults already encoded in
``ta._signals`` (RSI 70/30, Bollinger breakouts, regime/MACD/cross flags) — no
new config format. ``ta._signals`` emits a directional MACD/regime/cross string
for any coin with a real series, so in practice the only non-triggered coins are
stables and un-ingested coins (``ta=None`` → empty signals); those are summarized
in a single "quiet coins" line. A future user-tunable ``digest_rules.local.json``
(via ``paths.data_dir()``) is the documented extension point.

The render+IO structure mirrors ``dashboard.build()``: ``build_digest`` is a pure
string builder with an injected connection (Epic-14 pure-vs-IO split); ``build``
owns the DB + coins-config lifecycle.
"""
import json
import math
from datetime import UTC, datetime
from pathlib import Path

from domdhi_crypto.agent import context
from domdhi_crypto.shared import db, paths

# Factor values surfaced under each triggered coin as rationale prose. Curated to
# the most decision-relevant of the 44 BUILTIN_FACTORS; only those present and
# finite in the coin's factor_values are rendered.
_KEY_FACTORS = ("rsi_14", "macd_hist", "price_vs_sma20", "roc_10", "bb_pctb_20")


def _fmt_num(x, decimals: int = 2) -> str:
    """Format a number for the brief, coercing non-finite values to ``"n/a"``.

    Uses ``math.isfinite`` (NOT ``math.isnan``) so it rejects ±Infinity as well
    as NaN — both are non-renderable. (memory: json-safety-isnan-misses-infinity)
    """
    if not isinstance(x, (int, float)) or isinstance(x, bool):
        return "n/a"
    if not math.isfinite(float(x)):
        return "n/a"
    return f"{x:,.{decimals}f}"


def _fmt_money(x) -> str:
    """Money token: ``$1,000.00`` for finite values, bare ``n/a`` otherwise (no
    stray ``$`` sigil on the placeholder)."""
    s = _fmt_num(x)
    return f"${s}" if s != "n/a" else "n/a"


def _fmt_pct(x) -> str:
    """Signed percent token: ``+900.0%`` for finite values, ``n/a`` otherwise."""
    if not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(float(x)):
        return "n/a"
    return f"{x:+,.1f}%"


def _is_triggered(signals: list[str]) -> bool:
    """A coin triggers when any signal string is non-neutral (only the RSI line
    is ever 'neutral'; MACD/regime/cross strings are always directional)."""
    return any("neutral" not in s.lower() for s in signals)


def _coin_section(ctx: dict, coin: dict) -> str:
    """Render one triggered coin's Markdown section from its context dict."""
    symbol = ctx["symbol"]
    name = coin.get("name")
    heading = f"### {symbol}" + (f" — {name}" if name and name != symbol else "")

    pos = ctx["position"]
    price_s = _fmt_money(pos.get("price"))
    pl_s = _fmt_money(pos.get("pl"))
    # pl_pct is a meaningless 0.0 placeholder upstream when pl is None — show n/a
    # so the line never reads "$n/a (0.0%)".
    plpct_s = _fmt_pct(pos.get("pl_pct")) if pos.get("pl") is not None else "n/a"

    signals = ctx["signals"]["ta"]["signals"]
    signal_lines = "\n".join(f"- {s}" for s in signals)

    factor_values = ctx["signals"].get("factor_values", {})
    rendered = []
    for name_ in _KEY_FACTORS:
        if name_ not in factor_values:
            continue
        val = _fmt_num(factor_values[name_])
        if val != "n/a":
            rendered.append(f"{name_}={val}")
    factors_line = ("\n\n**Key factors:** " + " · ".join(rendered)) if rendered else ""

    return (
        f"{heading}\n\n"
        f"**Price:** {price_s} · **P/L:** {pl_s} ({plpct_s})\n\n"
        f"{signal_lines}"
        f"{factors_line}\n"
    )


def build_digest(coins_cfg: dict, *, conn) -> str:
    """Return the Markdown digest for *coins_cfg* (pure — no IO).

    Parameters
    ----------
    coins_cfg:
        Parsed ``coins.local.json`` dict with a ``"coins"`` list.
    conn:
        Open SQLite connection (caller owns the lifecycle).

    Returns
    -------
    str
        A valid, non-empty Markdown document with a dated header. When no coin
        has a triggered signal, the body is an explicit ``_No signals triggered._``
        line (never an empty string).
    """
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    header = f"# Domdhi Crypto Digest — {today}"

    sections: list[str] = []
    quiet: list[str] = []
    for coin in coins_cfg.get("coins", []):
        symbol = coin["symbol"]
        ctx = context.build_context(symbol, conn=conn, coins_cfg=coins_cfg)
        ta = ctx.get("signals", {}).get("ta") if "error" not in ctx else None
        signals = ta.get("signals", []) if ta else []
        if signals and _is_triggered(signals):
            sections.append(_coin_section(ctx, coin))
        else:
            quiet.append(symbol.upper())

    parts = [header]
    if sections:
        parts.append("## Triggered Signals")
        parts.extend(sections)
    else:
        parts.append("_No signals triggered._")
    if quiet:
        parts.append(f"**Quiet coins:** {', '.join(quiet)}")

    return "\n\n".join(parts) + "\n"


def _load_coins() -> dict:
    """Load coins config from the data dir (mirrors ``dashboard.build``'s loader
    to avoid a circular import on ``cli``)."""
    coins_path = paths.coins_path()
    if not coins_path.exists():
        raise SystemExit(
            f"Missing {paths.COINS_FILE}. Copy {paths.COINS_EXAMPLE} -> {paths.COINS_FILE}."
        )
    with open(coins_path, encoding="utf-8") as f:
        return json.load(f)


def build(out_path: Path | None = None, *, conn=None, coins_cfg: dict | None = None) -> Path:
    """Write the Markdown digest to *out_path* and return the path written.

    Parameters
    ----------
    out_path:
        Override output path. When ``None``, uses ``paths.digest_path()``.
    conn:
        Injected DB connection for testing. When ``None``, opens and closes its own.
    coins_cfg:
        Injected coins config for testing. When ``None``, loads from
        ``coins.local.json``.

    Returns
    -------
    Path
        The path written to.
    """
    own_conn = conn is None
    if coins_cfg is None:
        coins_cfg = _load_coins()
    if conn is None:
        conn = db.connect()
    try:
        md = build_digest(coins_cfg, conn=conn)
    finally:
        if own_conn:
            conn.close()

    out = Path(out_path) if out_path is not None else paths.digest_path()
    # Create the parent dir for an explicit --out override: the default
    # data_dir() always exists, but a user-supplied nested path would otherwise
    # raise a raw FileNotFoundError from write_text.
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    return out
