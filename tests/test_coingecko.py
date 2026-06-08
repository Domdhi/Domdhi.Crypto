"""Tests for the CoinGecko client — tier/header wiring and 429 backoff.

No network: the HTTP session is replaced with a fake, and time.sleep is
patched out so the backoff path runs instantly.
"""
from unittest.mock import MagicMock

import pytest

from domdhi_crypto.ingest import coingecko
from domdhi_crypto.ingest.coingecko import PRO_BASE, CoinGecko


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_demo_tier_uses_demo_host_and_header():
    cg = CoinGecko(config={"tier": "demo", "api_key": "CG-demo-key"})
    assert cg.base == coingecko.DEMO_BASE
    assert cg.session.headers["x-cg-demo-api-key"] == "CG-demo-key"
    assert "x-cg-pro-api-key" not in cg.session.headers


def test_pro_tier_uses_pro_host_and_header():
    cg = CoinGecko(config={"tier": "pro", "api_key": "CG-pro-key"})
    assert cg.base == PRO_BASE
    assert cg.session.headers["x-cg-pro-api-key"] == "CG-pro-key"
    assert "x-cg-demo-api-key" not in cg.session.headers


def test_tier_defaults_to_demo_when_unspecified():
    cg = CoinGecko(config={"api_key": "CG-x"})
    assert cg.base == coingecko.DEMO_BASE


def test_get_retries_after_429(monkeypatch):
    monkeypatch.setattr(coingecko.time, "sleep", lambda *_: None)  # no real waiting
    cg = CoinGecko(config={"api_key": "CG-x"}, pause=0)
    cg.session = MagicMock()
    cg.session.get.side_effect = [
        FakeResponse(429),
        FakeResponse(429),
        FakeResponse(200, payload={"ok": True}),
    ]
    result = cg._get("/ping")
    assert result == {"ok": True}
    assert cg.session.get.call_count == 3


def test_get_gives_up_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr(coingecko.time, "sleep", lambda *_: None)
    cg = CoinGecko(config={"api_key": "CG-x"}, pause=0)
    cg.session = MagicMock()
    cg.session.get.return_value = FakeResponse(429)
    with pytest.raises(RuntimeError, match="HTTP 429"):
        cg._get("/ping", retries=3)
    assert cg.session.get.call_count == 3


def test_coingecko_satisfies_prices_provider_protocol():
    # E20-S2: CoinGecko structurally conforms to the PricesProvider seam. The
    # Protocol is @runtime_checkable so isinstance verifies the method surface.
    from domdhi_crypto.ingest.prices_provider import PricesProvider

    cg = CoinGecko(config={"api_key": "CG-x"})
    assert isinstance(cg, PricesProvider)


def test_cmd_ingest_runs_end_to_end_via_seam(tmp_path, monkeypatch):
    """E20-S2 seam test: cmd_ingest drives a FakeProvider without touching CoinGecko.

    Proves the PricesProvider seam is wired end-to-end: a stand-in provider
    conforming to the Protocol drives the full ingest path, data lands in the DB,
    and zero CoinGecko / network code is exercised.
    """
    import types

    from domdhi_crypto import cli
    from domdhi_crypto.ingest.prices_provider import PricesProvider
    from domdhi_crypto.shared import db

    # --------------------------------------------------------------------- #
    # Minimal payloads that satisfy cmd_ingest's data expectations            #
    # --------------------------------------------------------------------- #
    TS = 1_700_000_000_000  # arbitrary epoch ms

    class FakeProvider:
        """Structurally conforms to PricesProvider — no inheritance needed."""

        def markets(self, ids, vs="usd"):
            return [
                {
                    "id": "bitcoin",
                    "symbol": "btc",
                    "name": "Bitcoin",
                    "current_price": 30_000.0,
                    "market_cap": 600_000_000_000,
                    "price_change_percentage_24h_in_currency": 1.5,
                    "price_change_percentage_7d_in_currency": 3.0,
                    "price_change_percentage_30d_in_currency": -2.0,
                }
            ]

        def market_chart(self, coin_id, days=365, vs="usd"):
            return {
                "prices": [[TS, 30_000.0]],
                "total_volumes": [[TS, 1_000_000.0]],
                "market_caps": [[TS, 600_000_000_000.0]],
            }

        def ohlc(self, coin_id, days=365, vs="usd"):
            return [[TS, 29_900.0, 30_100.0, 29_800.0, 30_000.0]]

    # Verify FakeProvider satisfies the Protocol
    assert isinstance(FakeProvider(), PricesProvider)

    # --------------------------------------------------------------------- #
    # Wire monkeypatches                                                      #
    # --------------------------------------------------------------------- #
    dbfile = tmp_path / "t.db"
    db.init_db(dbfile)

    # Patch load_coins to return a minimal single-coin config
    monkeypatch.setattr(cli, "load_coins", lambda: {
        "coins": [{"id": "bitcoin", "symbol": "BTC"}],
        "vs_currency": "usd",
    })

    # Capture the real functions BEFORE patching: cli.db IS the db module object,
    # so patching cli.db.init_db / cli.db.connect also rebinds db.init_db /
    # db.connect in-place.  A lambda that referenced db.init_db after the patch
    # would recurse into itself.  Bind the originals explicitly (same pattern as
    # factors_env in test_cli.py uses for connect).
    _orig_init_db = db.init_db
    _orig_connect = db.connect

    monkeypatch.setattr(cli.db, "init_db", lambda db_file=None: _orig_init_db(dbfile))
    monkeypatch.setattr(cli.db, "connect", lambda db_file=None: _orig_connect(dbfile))

    # Patch the seam: get_provider returns our FakeProvider
    monkeypatch.setattr(cli.prices_provider, "get_provider", lambda: FakeProvider())

    # --------------------------------------------------------------------- #
    # Run ingest and verify data landed                                       #
    # --------------------------------------------------------------------- #
    cli.cmd_ingest(types.SimpleNamespace(days=1))

    conn = _orig_connect(dbfile)
    series = db.load_close_series(conn, "bitcoin")
    conn.close()
    assert series is not None, "Expected price series for bitcoin after ingest"


def test_markets_builds_expected_request(monkeypatch):
    monkeypatch.setattr(coingecko.time, "sleep", lambda *_: None)
    cg = CoinGecko(config={"api_key": "CG-x"}, pause=0)
    cg.session = MagicMock()
    cg.session.get.return_value = FakeResponse(200, payload=[{"id": "bitcoin"}])
    out = cg.markets(["bitcoin", "ethereum"])
    assert out == [{"id": "bitcoin"}]
    _, kwargs = cg.session.get.call_args
    params = kwargs["params"]
    assert params["ids"] == "bitcoin,ethereum"
    assert params["price_change_percentage"] == "24h,7d,30d"
    assert params["per_page"] == 2
