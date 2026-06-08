"""Tests for cli.py — the pure helpers (coin resolver, version resolver) plus the
``factors`` subcommand (E13-S2). The helper tests are network-free. The
``factors`` tests drive the command end-to-end against an in-memory-style temp
DB, with ``load_coins`` and ``db.connect`` monkeypatched so no real config or
CoinGecko is touched.
"""

import sys
from importlib.metadata import version

import numpy as np
import pandas as pd
import pytest

from domdhi_crypto import cli
from domdhi_crypto.cli import _resolve, _version
from domdhi_crypto.report import digest
from domdhi_crypto.shared import db, paths

COINS = [
    {"id": "bitcoin", "symbol": "BTC"},
    {"id": "ethereum", "symbol": "ETH"},
]


def test_resolve_matches_by_symbol():
    assert _resolve(COINS, "BTC") is COINS[0]


def test_resolve_matches_by_id():
    assert _resolve(COINS, "bitcoin") is COINS[0]


def test_resolve_symbol_and_id_return_same_coin():
    assert _resolve(COINS, "BTC") is _resolve(COINS, "bitcoin")


def test_resolve_is_case_insensitive():
    assert _resolve(COINS, "btc") is COINS[0]
    assert _resolve(COINS, "BITCOIN") is COINS[0]


def test_resolve_returns_none_on_miss():
    assert _resolve(COINS, "nope") is None


def test_version_matches_package_metadata():
    assert _version() == version("domdhi-crypto")


# --------------------------------------------------------------------------- #
# factors subcommand (E13-S2)
# --------------------------------------------------------------------------- #

@pytest.fixture
def factors_env(tmp_path, monkeypatch):
    """Temp DB with a populated bitcoin price history; dogecoin known but empty.

    ``load_coins`` and ``db.connect`` are monkeypatched so ``cmd_factors`` runs
    against the temp DB with no real config/network.
    """
    dbfile = tmp_path / "t.db"
    db.init_db(dbfile)
    conn = db.connect(dbfile)
    n = 260
    base = pd.Timestamp("2023-01-01")
    rng = np.random.default_rng(0)
    walk = np.abs(np.cumsum(rng.standard_normal(n))) + 50.0  # strictly positive
    rows = [
        (
            (base + pd.Timedelta(days=i)).strftime("%Y-%m-%d"),
            float(walk[i]),
            float(abs(rng.standard_normal()) * 1000 + 100),
            None,
        )
        for i in range(n)
    ]
    db.upsert_coin(conn, "bitcoin", "BTC", "Bitcoin")
    db.upsert_prices(conn, "bitcoin", rows)
    # daily OHLC candles for bitcoin so the --ohlc path (high/low factors) is testable
    ohlc_rows = [
        (
            int((base + pd.Timedelta(days=i)).tz_localize("UTC").timestamp() * 1000),
            float(walk[i]),
            float(walk[i]) + 2.0,
            float(walk[i]) - 2.0,
            float(walk[i]) + 0.5,
        )
        for i in range(n)
    ]
    db.upsert_ohlc(conn, "bitcoin", ohlc_rows)
    # a short-series coin (5 days) to exercise the insufficient-data warning
    short_rows = [
        ((base + pd.Timedelta(days=i)).strftime("%Y-%m-%d"), float(50 + i), 100.0, None)
        for i in range(5)
    ]
    db.upsert_coin(conn, "shorty", "SHORT", "Shorty")
    db.upsert_prices(conn, "shorty", short_rows)
    conn.commit()
    conn.close()

    coins = {
        "coins": [
            {"id": "bitcoin", "symbol": "BTC"},
            {"id": "dogecoin", "symbol": "DOGE"},
            {"id": "tether", "symbol": "USDT", "stable": True},
            {"id": "shorty", "symbol": "SHORT"},
        ],
        "vs_currency": "usd",
    }
    monkeypatch.setattr(cli, "load_coins", lambda: coins)
    # Capture the real connect BEFORE patching: cli.db IS the db module object, so
    # patching cli.db.connect also rebinds db.connect — a lambda that called
    # db.connect(dbfile) would recurse into itself. Bind the original explicitly.
    _orig_connect = db.connect
    monkeypatch.setattr(cli.db, "connect", lambda db_file=None: _orig_connect(dbfile))
    return dbfile


def _run(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["domdhi-crypto", *argv])
    cli.main()


def test_cmd_factors_is_registered():
    """The handler exists and is wired (factors sub-parser dispatches to it)."""
    assert callable(cli.cmd_factors)


def test_factors_command_prints_a_ranked_table(factors_env, monkeypatch, capsys):
    _run(monkeypatch, "factors", "BTC")
    out = capsys.readouterr().out
    # at least one known built-in factor name appears
    assert "rsi_14" in out or "roc_10" in out
    # report-style table has a dashed rule separator
    assert "-" * 10 in out


def test_factors_top_flag_limits_rows(factors_env, monkeypatch, capsys):
    _run(monkeypatch, "factors", "BTC")
    full = capsys.readouterr().out
    _run(monkeypatch, "factors", "BTC", "--top", "3")
    limited = capsys.readouterr().out
    assert limited.count("\n") < full.count("\n")


def test_factors_horizon_flag_is_accepted(factors_env, monkeypatch, capsys):
    _run(monkeypatch, "factors", "BTC", "--horizon", "10")
    out = capsys.readouterr().out
    assert "rsi_14" in out or "roc_10" in out


def test_factors_unknown_symbol_exits(factors_env, monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "factors", "NOTACOIN")


def test_factors_no_data_exits(factors_env, monkeypatch):
    # dogecoin is a known coin but has no ingested prices -> load_close_series None
    with pytest.raises(SystemExit):
        _run(monkeypatch, "factors", "DOGE")


# --------------------------------------------------------------------------- #
# backtest subcommand (wires engine.run_backtest + attribution)
# --------------------------------------------------------------------------- #

def test_cmd_backtest_is_registered():
    assert callable(cli.cmd_backtest)


def test_backtest_command_prints_summary_and_factor(factors_env, monkeypatch, capsys):
    _run(monkeypatch, "backtest", "BTC")
    out = capsys.readouterr().out
    assert "Total return" in out
    assert "Max drawdown" in out
    # the default factor name appears (in the header, and the by-factor table if traded)
    assert "price_vs_sma20" in out


def test_backtest_accepts_factor_and_cost_flags(factors_env, monkeypatch, capsys):
    _run(monkeypatch, "backtest", "BTC", "--factor", "rsi_centered",
         "--entry", "0", "--exit", "0", "--slippage-bps", "5", "--fee-rate", "0.001")
    out = capsys.readouterr().out
    assert "rsi_centered" in out


def test_backtest_unknown_symbol_exits(factors_env, monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "backtest", "NOTACOIN")


def test_backtest_no_data_exits(factors_env, monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "backtest", "DOGE")


def test_backtest_unknown_factor_exits(factors_env, monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "backtest", "BTC", "--factor", "not_a_real_factor")


# --------------------------------------------------------------------------- #
# --ohlc path (high/low factors via db.load_ohlcv_daily) — E20 follow-up
# --------------------------------------------------------------------------- #

def test_factors_ohlc_flag_scores_high_low_factors(factors_env, monkeypatch, capsys):
    _run(monkeypatch, "factors", "BTC", "--ohlc")
    out = capsys.readouterr().out
    # the previously-deferred high/low factors are now listed in the ranked table
    assert "williams_r_14" in out
    assert "adx_14" in out


def test_backtest_ohlc_runs_a_high_low_factor(factors_env, monkeypatch, capsys):
    _run(monkeypatch, "backtest", "BTC", "--ohlc", "--factor", "williams_r_14",
         "--entry", "-50", "--exit", "-80")
    out = capsys.readouterr().out
    assert "williams_r_14" in out
    assert "Total return" in out


def test_factors_ohlc_no_candle_data_exits(factors_env, monkeypatch):
    # dogecoin is a known coin but has neither prices nor ohlc candles ingested
    with pytest.raises(SystemExit):
        _run(monkeypatch, "factors", "DOGE", "--ohlc")


# --------------------------------------------------------------------------- #
# Input-validation + stablecoin + short-series guards (sweep follow-up)
# --------------------------------------------------------------------------- #

def test_factors_stablecoin_exits(factors_env, monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "factors", "USDT")


def test_backtest_stablecoin_exits(factors_env, monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "backtest", "USDT")


def test_ta_stablecoin_exits(factors_env, monkeypatch):
    # E20-S3: cmd_ta is the canonical guard definition (cli.py) but was the only
    # symbol-bearing command without a stablecoin-exit test. USDT is flagged stable
    # in the factors_env fixture, so `ta USDT` must SystemExit (no "Run: ingest"
    # dead-end), mirroring the factors/backtest/arena guards.
    with pytest.raises(SystemExit):
        _run(monkeypatch, "ta", "USDT")


def test_factors_rejects_nonpositive_horizon(factors_env, monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "factors", "BTC", "--horizon", "0")


def test_factors_rejects_nonpositive_top(factors_env, monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "factors", "BTC", "--top", "0")


def test_backtest_rejects_nonpositive_cash(factors_env, monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "backtest", "BTC", "--cash", "0")


def test_backtest_rejects_negative_fee(factors_env, monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "backtest", "BTC", "--fee-rate", "-0.1")


def test_short_series_warns(factors_env, monkeypatch, capsys):
    _run(monkeypatch, "factors", "SHORT")
    out = capsys.readouterr().out
    assert "may be unreliable" in out


# --------------------------------------------------------------------------- #
# mcp subcommand (E14-S4) — launch handler + optional-extra guard
# --------------------------------------------------------------------------- #

def test_cmd_mcp_is_registered():
    """The handler exists and is wired (the `mcp` sub-parser dispatches to it)."""
    assert callable(cli.cmd_mcp)


def test_mcp_subcommand_help_exits_zero(monkeypatch):
    # `domdhi-crypto mcp --help` must parse and exit 0 (subcommand is discoverable),
    # WITHOUT launching the blocking server.
    monkeypatch.setattr(sys, "argv", ["domdhi-crypto", "mcp", "--help"])
    with pytest.raises(SystemExit) as ei:
        cli.main()
    assert ei.value.code == 0


def test_cmd_mcp_missing_extra_exits_with_hint(monkeypatch):
    # When the optional `mcp` extra is absent, build_server()'s lazy import raises
    # ImportError; cmd_mcp must convert it to a SystemExit with an install hint —
    # never an unhandled traceback. Simulate by making run() raise ImportError.
    from domdhi_crypto_mcp import server as mcp_server

    def _raise():
        raise ImportError("No module named 'mcp'")

    monkeypatch.setattr(mcp_server, "run", _raise)
    with pytest.raises(SystemExit) as ei:
        cli.cmd_mcp(None)
    msg = str(ei.value).lower()
    assert "mcp" in msg and "install" in msg


# --------------------------------------------------------------------------- #
# digest subcommand (E15-S1.2)
# --------------------------------------------------------------------------- #

@pytest.fixture
def digest_env(tmp_path, monkeypatch):
    """tmp DB with a populated bitcoin history + snapshot; coins loader and DB
    connect wired to the temp DB, output isolated to tmp_path via the data dir.

    ``digest.build()`` loads coins via ``digest._load_coins`` (NOT ``cli.load_coins``
    — it deliberately avoids importing cli to prevent a circular import) and opens
    its connection via ``db.connect``, so those are the real wiring targets.
    """
    dbfile = tmp_path / "t.db"
    db.init_db(dbfile)
    conn = db.connect(dbfile)
    base = pd.Timestamp("2023-01-01")
    rows = [
        ((base + pd.Timedelta(days=i)).strftime("%Y-%m-%d"), float(50 + i), 100.0, None)
        for i in range(260)
    ]
    db.upsert_coin(conn, "bitcoin", "BTC", "Bitcoin")
    db.upsert_prices(conn, "bitcoin", rows)
    db.insert_snapshot(conn, "bitcoin", "2023-09-18T00:00:00Z", 1000.0, None, None, None, None)
    conn.commit()
    conn.close()

    coins = {"coins": [{"id": "bitcoin", "symbol": "BTC", "amount": 0.5, "avg_entry": 100}],
             "vs_currency": "usd"}
    # Isolate digest_path() to tmp_path and wire the loader + connection.
    monkeypatch.setenv("DOMDHI_CRYPTO_HOME", str(tmp_path))
    monkeypatch.setattr(digest, "_load_coins", lambda: coins)
    # Capture the real connect BEFORE patching (db is the same module object that
    # digest.db references) — a lambda calling db.connect() would recurse forever.
    _orig_connect = db.connect
    monkeypatch.setattr(db, "connect", lambda db_file=None: _orig_connect(dbfile))
    return tmp_path


def test_cmd_digest_is_registered():
    """The handler exists and is wired (digest sub-parser dispatches to it)."""
    assert callable(cli.cmd_digest)


def test_digest_command_writes_brief_and_reports_path(digest_env, monkeypatch, capsys):
    _run(monkeypatch, "digest")
    out = capsys.readouterr().out
    # Resolves to data_dir()/digest.md (data_dir == DOMDHI_CRYPTO_HOME == tmp_path).
    expected = paths.digest_path()
    assert expected == digest_env / "digest.md"
    assert expected.exists()
    assert out.startswith("Wrote ")
    assert str(expected) in out
    # The written brief actually summarizes the triggered coin (not an empty stub).
    assert "BTC" in expected.read_text(encoding="utf-8")


def test_digest_command_honors_out_override(digest_env, monkeypatch, capsys):
    target = digest_env / "sub" / "brief.md"
    target.parent.mkdir()
    _run(monkeypatch, "digest", "--out", str(target))
    out = capsys.readouterr().out
    assert target.exists()
    assert str(target) in out
    # Default location is NOT written when --out is given.
    assert not (digest_env / "digest.md").exists()


# --------------------------------------------------------------------------- #
# arena subcommand (E19-S3 — wires arena.run_arena: cortex vs baselines)
# --------------------------------------------------------------------------- #

def test_cmd_arena_is_registered():
    assert callable(cli.cmd_arena)


def test_arena_command_prints_cortex_vs_baselines(factors_env, monkeypatch, capsys):
    _run(monkeypatch, "arena", "BTC")
    out = capsys.readouterr().out
    # cortex + both baselines (buy-and-hold + the default rule baseline) are listed
    assert "cortex" in out
    assert "buy_and_hold" in out
    assert "price_vs_sma50" in out  # default baseline factor
    # relative performance ("vs cortex") column is present
    assert "vs cortex" in out.lower()


def test_arena_reports_cortex_factor_and_attribution_header(factors_env, monkeypatch, capsys):
    _run(monkeypatch, "arena", "BTC", "--factor", "rsi_centered", "--entry", "0", "--exit", "0")
    out = capsys.readouterr().out
    assert "rsi_centered" in out  # cortex factor surfaces (header + attribution table)
    assert "By factor" in out


def test_arena_accepts_baseline_and_cost_flags(factors_env, monkeypatch, capsys):
    _run(monkeypatch, "arena", "BTC", "--baseline-factor", "price_vs_sma20",
         "--slippage-bps", "5", "--fee-rate", "0.001")
    out = capsys.readouterr().out
    assert "price_vs_sma20" in out


def test_arena_unknown_symbol_exits(factors_env, monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "arena", "NOTACOIN")


def test_arena_no_data_exits(factors_env, monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "arena", "DOGE")


def test_arena_stablecoin_exits(factors_env, monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "arena", "USDT")


def test_arena_unknown_cortex_factor_exits(factors_env, monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "arena", "BTC", "--factor", "not_a_real_factor")


def test_arena_unknown_baseline_factor_exits(factors_env, monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "arena", "BTC", "--baseline-factor", "not_a_real_factor")


def test_arena_rejects_nonpositive_cash(factors_env, monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "arena", "BTC", "--cash", "0")


# --------------------------------------------------------------------------- #
# multi-factor cortex (comma-separated --factor → first-rule-wins cascade)
# --------------------------------------------------------------------------- #

def test_arena_accepts_multi_factor_cortex(factors_env, monkeypatch, capsys):
    _run(monkeypatch, "arena", "BTC", "--factor", "rsi_centered,price_vs_sma20")
    out = capsys.readouterr().out
    # the raw comma list surfaces in the header; both members are valid factors
    assert "rsi_centered,price_vs_sma20" in out
    assert "cortex" in out


def test_arena_multi_factor_unknown_member_exits(factors_env, monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "arena", "BTC", "--factor", "rsi_centered,not_a_real_factor")


def test_walkforward_accepts_multi_factor_cortex(factors_env, monkeypatch, capsys):
    _run(monkeypatch, "walkforward", "BTC", "--factor", "rsi_centered,price_vs_sma20")
    out = capsys.readouterr().out
    assert "rsi_centered,price_vs_sma20" in out


# --------------------------------------------------------------------------- #
# walkforward subcommand (E20-S5 — wires walkforward.walk_forward fold segmentation)
# --------------------------------------------------------------------------- #

def test_cmd_walkforward_is_registered():
    assert callable(cli.cmd_walkforward)


def test_walkforward_command_prints_folds_and_aggregates(factors_env, monkeypatch, capsys):
    _run(monkeypatch, "walkforward", "BTC")
    out = capsys.readouterr().out
    assert "walk-forward" in out
    assert "FOLD" in out and "EDGE%" in out
    assert "win rate" in out.lower()
    assert "4 folds" in out  # default fold count


def test_walkforward_accepts_folds_flag(factors_env, monkeypatch, capsys):
    _run(monkeypatch, "walkforward", "BTC", "--folds", "6")
    out = capsys.readouterr().out
    assert "6 folds" in out


def test_walkforward_accepts_cost_flags(factors_env, monkeypatch, capsys):
    _run(monkeypatch, "walkforward", "BTC", "--factor", "rsi_centered",
         "--entry", "0", "--exit", "0", "--slippage-bps", "5", "--fee-rate", "0.001")
    out = capsys.readouterr().out
    assert "rsi_centered" in out


def test_walkforward_rejects_nonpositive_folds(factors_env, monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "walkforward", "BTC", "--folds", "0")


def test_walkforward_folds_exceeding_bars_exits(factors_env, monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "walkforward", "BTC", "--folds", "999999")


def test_walkforward_rejects_nonpositive_cash(factors_env, monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "walkforward", "BTC", "--cash", "0")


def test_walkforward_unknown_symbol_exits(factors_env, monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "walkforward", "NOTACOIN")


def test_walkforward_no_data_exits(factors_env, monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "walkforward", "DOGE")


def test_walkforward_stablecoin_exits(factors_env, monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "walkforward", "USDT")


def test_walkforward_unknown_factor_exits(factors_env, monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "walkforward", "BTC", "--factor", "not_a_real_factor")
