"""Tests for dashboard.py — the offline HTML dashboard (Epic 18).

Cycle-3 surfaces the decision layer (ledger/risk/factors/backtest) in the
offline dashboard with interactive **vendored uPlot** charts (ADR-009). These
tests assert the AC for E18-S1..S5.

``dashboard.build()`` reads its inputs from ``paths.data_dir()`` (driven by
``$DOMDHI_CRYPTO_HOME``) and writes ``dashboard.html`` there, so the fixture
points that env var at a tmp dir, seeds a tmp DB, and writes a tmp
``coins.local.json`` — no real config/network is touched.
"""
import json
from pathlib import Path

import pandas as pd
import pytest

from domdhi_crypto.report import dashboard
from domdhi_crypto.report.dashboard import charts, panels, scaffold
from domdhi_crypto.shared import db

REPO_ROOT = Path(__file__).resolve().parents[1]
VENDOR = Path(dashboard.__file__).parent / "vendor"


def _seed_ramp(conn, coin_id, symbol, name, n=260, start=50.0):
    """Seed a strictly-increasing daily close series (known-bull TA outcome)."""
    base = pd.Timestamp("2023-01-01")
    rows = [
        ((base + pd.Timedelta(days=i)).strftime("%Y-%m-%d"), float(start + i), 100.0, None)
        for i in range(n)
    ]
    db.upsert_coin(conn, coin_id, symbol, name)
    db.upsert_prices(conn, coin_id, rows)


@pytest.fixture
def dash_env(tmp_path, monkeypatch):
    """tmp data dir with a seeded DB (BTC + ETH ramps, snapshots) and coins cfg.

    Returns the tmp data dir; ``dashboard.build()`` reads/writes there.
    """
    monkeypatch.setenv("DOMDHI_CRYPTO_HOME", str(tmp_path))
    dbfile = tmp_path / "crypto.db"
    db.init_db(dbfile)
    conn = db.connect(dbfile)
    _seed_ramp(conn, "bitcoin", "BTC", "Bitcoin", start=50.0)
    db.insert_snapshot(conn, "bitcoin", "2023-09-18T00:00:00Z", 1000.0, None, None, None, None)
    _seed_ramp(conn, "ethereum", "ETH", "Ethereum", start=20.0)
    db.insert_snapshot(conn, "ethereum", "2023-09-18T00:00:00Z", 400.0, None, None, None, None)
    # transactions so the ledger/NAV/P-L panels have data
    db.insert_transaction(conn, "bitcoin", "2023-02-01T00:00:00Z", "buy", 0.5, 80.0, 0.0)
    db.insert_transaction(conn, "ethereum", "2023-02-01T00:00:00Z", "buy", 2.0, 30.0, 0.0)
    conn.commit()
    conn.close()
    coins = {
        "vs_currency": "usd",
        "coins": [
            {"id": "bitcoin", "symbol": "BTC", "amount": 0.5, "avg_entry": 80},
            {"id": "ethereum", "symbol": "ETH", "amount": 2.0, "avg_entry": 30},
        ],
    }
    (tmp_path / "coins.local.json").write_text(json.dumps(coins), encoding="utf-8")
    return tmp_path


@pytest.fixture
def built_html(dash_env):
    """Generate the dashboard and return its HTML text."""
    out = dashboard.build()
    return out.read_text(encoding="utf-8")


@pytest.fixture
def dash_env_empty(tmp_path, monkeypatch):
    """tmp data dir with coins configured but NO price history / NO transactions —
    exercises the graceful-degrade ("n/a"/empty, never error) branches."""
    monkeypatch.setenv("DOMDHI_CRYPTO_HOME", str(tmp_path))
    dbfile = tmp_path / "crypto.db"
    db.init_db(dbfile)
    conn = db.connect(dbfile)
    db.upsert_coin(conn, "bitcoin", "BTC", "Bitcoin")  # known coin, no prices
    conn.commit()
    conn.close()
    coins = {"vs_currency": "usd", "coins": [
        {"id": "bitcoin", "symbol": "BTC", "amount": 0.5, "avg_entry": 80}]}
    (tmp_path / "coins.local.json").write_text(json.dumps(coins), encoding="utf-8")
    return tmp_path


@pytest.fixture
def empty_html(dash_env_empty):
    """Generate the dashboard against the empty fixture (must not raise)."""
    return dashboard.build().read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# E18-S1 — vendored uPlot substrate + panel seam
# --------------------------------------------------------------------------- #

def test_s1_vendored_asset_with_provenance():
    """AC: uPlot committed as a static asset with version + source URL + license."""
    js = VENDOR / "uplot.min.js"
    css = VENDOR / "uplot.min.css"
    readme = VENDOR / "README.md"
    assert js.exists() and js.stat().st_size > 10_000, "uplot.min.js missing/too small"
    assert css.exists() and css.stat().st_size > 200, "uplot.min.css missing/too small"
    txt = readme.read_text(encoding="utf-8")
    assert "1.6.31" in txt, "vendor README must record the uPlot version"
    assert "MIT" in txt, "vendor README must record the license"
    assert "github.com/leeoniya/uPlot" in txt, "vendor README must record the source URL"


def test_s1_uplot_inlined_not_cdn(built_html):
    """AC: dashboard.py inlines the uPlot JS+CSS — not a CDN link."""
    # The vendored library is present inline (its IIFE banner/source).
    assert "uPlot=function" in built_html, "uPlot library not inlined into the HTML"
    # No external resource references — fully offline.
    assert 'src="http' not in built_html, "found an external <script src> — not offline"
    assert 'href="http' not in built_html, "found an external href resource — not offline"
    assert "unpkg" not in built_html and "cdn." not in built_html, "CDN reference present"


def test_s1_offline_interactive_chart(built_html):
    """AC: the generated HTML renders at least one interactive uPlot chart."""
    assert "new uPlot(" in built_html, "no uPlot chart instantiated in the output"


def test_s1_core_deps_unchanged():
    """AC: pyproject runtime core dependencies unchanged (3 deps; ADR-007)."""
    import tomllib

    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    deps = data["project"]["dependencies"]
    assert len(deps) == 3, f"core deps must stay at 3 (ADR-007), got {deps}"
    assert not any("uplot" in d.lower() for d in deps), "uPlot must not be a Python dep"


def test_s1_panel_seam_exists():
    """AC: a panel-assembly seam exists so S2-S5 add panels without rewriting build()."""
    assert "{panels}" in scaffold._TEMPLATE, "template lacks a {panels} assembly slot"
    assert hasattr(panels, "_PANEL_FUNCS"), "no _PANEL_FUNCS panel registry"
    assert isinstance(panels._PANEL_FUNCS, list) and panels._PANEL_FUNCS


def test_s1_build_is_offline_and_nonempty(built_html):
    """A built dashboard is a non-trivial self-contained HTML document."""
    assert built_html.lstrip().startswith("<!doctype html>")
    assert len(built_html) > 20_000, "inlined uPlot should make the doc sizeable"


def test_s1_proof_panel_renders_with_data(built_html):
    """The S1 proof panel actually renders (div + a non-empty baked data array),
    exercising _epoch_seconds + the NaN->None mapping, not just lib presence."""
    assert 'id="proof-chart"' in built_html, "proof chart div missing from output"
    # the baked payload carries a data array with real numbers (epoch x-values)
    assert '"data":[[' in built_html.replace(" ", ""), "no baked chart data array"


def test_s1_json_script_hardens_script_breakout():
    """_json_script must neutralise a '</script>' breakout in baked data."""
    out = charts._json_script({"sym": "BTC</script><b>x"})
    assert "</script>" not in out, "raw </script> leaked into inline-script payload"
    assert "<\\/script>" in out, "expected the </ sequence to be escaped"


# --------------------------------------------------------------------------- #
# E18-S2 — NAV + P/L panel
# --------------------------------------------------------------------------- #

def test_s2_nav_curve_and_pl_render(built_html):
    """AC: dated NAV line + realized/unrealized P/L figures render from ledger."""
    assert "Portfolio · NAV &amp; P/L" in built_html or "NAV" in built_html
    assert 'id="nav-chart"' in built_html, "NAV uPlot chart missing"
    assert "Realized P/L" in built_html and "Unrealized P/L" in built_html
    # the fixture has open positions marked above cost → unrealized P/L is finite money
    assert built_html.count("$") >= 2, "P/L figures not money-formatted"


def test_s2_nav_panel_degrades_when_empty(empty_html):
    """AC: no transactions/holdings data → panel degrades (no chart), never errors."""
    # build() did not raise (fixture would have surfaced it). NAV chart is omitted
    # because there is no price series to plot, but the page still renders.
    assert 'id="nav-chart"' not in empty_html
    assert empty_html.lstrip().startswith("<!doctype html>")


# --------------------------------------------------------------------------- #
# E18-S3 — Risk panel
# --------------------------------------------------------------------------- #

def test_s3_risk_panel_renders(built_html):
    """AC: correlation view + vol + beta + max-drawdown render from risk.py."""
    assert ">Risk<" in built_html, "Risk panel title missing"
    assert "Portfolio Vol" in built_html
    assert "Max Drawdown" in built_html
    assert 'class="corr"' in built_html, "correlation table missing (>=2 coins w/ history)"
    assert "β" in built_html, "beta-to-BTC figure(s) missing"


def test_s3_risk_nan_surfaces_as_na(empty_html):
    """AC: NaN / under-window outputs surface as 'n/a', never fabricated/crash."""
    assert ">Risk<" in empty_html, "Risk panel should still render its figures"
    assert "n/a" in empty_html, "expected n/a placeholders for under-window risk"
    # a raw 'nan' must never leak into the rendered figures
    head = empty_html.lower().split("uplot=function")[0]  # exclude the inlined lib
    assert "nan%" not in head and ">nan<" not in head, "raw NaN leaked into a figure"
    assert 'class="corr"' not in empty_html, "correlation table omitted when <2 coins"


# --------------------------------------------------------------------------- #
# E18-S4 — Triggered-signals view
# --------------------------------------------------------------------------- #

def test_s4_triggered_signals_listed(built_html):
    """AC: per-coin currently-triggered signals are listed with their values."""
    assert "Triggered Signals" in built_html, "signals panel missing"
    # the seeded ramps are monotonic-up → bull/golden-cross/MACD+ signals fire
    assert 'class="siglist"' in built_html, "no per-coin signal list rendered"
    # at least one seeded coin symbol appears inside the signals panel
    panel = built_html.split("Triggered Signals", 1)[1]
    assert "BTC" in panel or "ETH" in panel, "triggered coin symbol not shown"


def test_s4_signals_skip_no_data_coin(empty_html):
    """AC: a coin with no data is skipped (panel omitted), never errors."""
    # BTC has no price series → ta=None → not triggered → panel omitted entirely.
    assert "Triggered Signals" not in empty_html
    assert empty_html.lstrip().startswith("<!doctype html>")


# --------------------------------------------------------------------------- #
# E18-S5 — Backtest equity curve + attribution
# --------------------------------------------------------------------------- #

def test_s5_backtest_curve_and_attribution(built_html):
    """AC: a backtest run's equity curve (uPlot) + per-factor attribution table."""
    assert "Backtest" in built_html, "backtest panel missing"
    # div id keys off the coin id (unique), not the symbol (tickers can collide)
    assert 'id="bt-bitcoin"' in built_html or 'id="bt-ethereum"' in built_html, \
        "no equity-curve uPlot chart rendered"
    assert 'class="attr"' in built_html, "attribution table missing"
    assert "price_vs_sma20" in built_html, "default-rule factor not shown in attribution"


def test_s5_backtest_omitted_when_no_run(empty_html):
    """AC: absent a backtest run (no priced coins), the panel is omitted, no error."""
    assert "Backtest" not in empty_html
    assert empty_html.lstrip().startswith("<!doctype html>")


# --------------------------------------------------------------------------- #
# Cross-cutting — HTML-injection safety (code-review MAJOR-1)
# --------------------------------------------------------------------------- #

def test_user_symbols_cannot_inject_markup(tmp_path, monkeypatch):
    """A user-authored coin symbol with a `</script>` payload must not break out of
    its context: escaped in HTML body/attribute contexts, and `</` neutralised in
    inline-script (uPlot JSON) contexts — never injected as live markup."""
    nasty = "</script><b>pwn"
    monkeypatch.setenv("DOMDHI_CRYPTO_HOME", str(tmp_path))
    dbfile = tmp_path / "crypto.db"
    db.init_db(dbfile)
    conn = db.connect(dbfile)
    _seed_ramp(conn, "evil", nasty, "Evil", start=10.0)
    db.insert_snapshot(conn, "evil", "2023-09-18T00:00:00Z", 5.0, None, None, None, None)
    db.insert_transaction(conn, "evil", "2023-02-01T00:00:00Z", "buy", 1.0, 4.0, 0.0)
    conn.commit()
    conn.close()
    (tmp_path / "coins.local.json").write_text(json.dumps({"vs_currency": "usd", "coins": [
        {"id": "evil", "symbol": nasty, "amount": 1.0, "avg_entry": 4}]}), encoding="utf-8")
    out = dashboard.build().read_text(encoding="utf-8")
    # no <script> breakout anywhere (body escaped to &lt;/script&gt;, payload to <\/script>)
    assert "</script><b>pwn" not in out, "symbol broke out of its context (injection)"
    # body/attribute contexts escaped the markup
    assert "&lt;/script&gt;&lt;b&gt;pwn" in out, "symbol not HTML-escaped in body"
