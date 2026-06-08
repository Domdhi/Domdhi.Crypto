"""CoinGecko API client. Supports demo (free) and pro tiers.

Reads credentials from config.local.json in the data directory (gitignored).
The only difference between tiers is the base URL and the auth header name,
both handled here.
"""
import json
import time

from domdhi_crypto.shared import paths

DEMO_BASE = "https://api.coingecko.com/api/v3"
PRO_BASE = "https://pro-api.coingecko.com/api/v3"


def load_config():
    config_path = paths.config_path()
    if not config_path.exists():
        raise SystemExit(
            f"Missing {paths.CONFIG_FILE}. Copy {paths.CONFIG_EXAMPLE} -> {paths.CONFIG_FILE} "
            f"and paste your CoinGecko API key."
        )
    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)
    key = cfg.get("api_key", "")
    if not key or "PASTE" in key:
        raise SystemExit(f"Set your CoinGecko API key in {paths.CONFIG_FILE}.")
    return cfg


class CoinGecko:
    """Thin wrapper with rate-limit backoff and a polite inter-call pause.

    Structurally conforms to ``ingest.prices_provider.PricesProvider`` — no
    inheritance or import required; conformance is by shape.
    """

    def __init__(self, config=None, pause=2.0):
        import requests

        cfg = config or load_config()
        self.tier = cfg.get("tier", "demo").lower()
        self.api_key = cfg["api_key"]
        self.pause = pause
        self.session = requests.Session()
        self.session.headers["accept"] = "application/json"
        if self.tier == "pro":
            self.base = PRO_BASE
            self.session.headers["x-cg-pro-api-key"] = self.api_key
        else:
            self.base = DEMO_BASE
            self.session.headers["x-cg-demo-api-key"] = self.api_key

    def _get(self, path, params=None, retries=4):
        url = f"{self.base}{path}"
        last = None
        for attempt in range(retries):
            r = self.session.get(url, params=params, timeout=30)
            last = r
            if r.status_code == 429:
                wait = 5 * (2 ** attempt)
                print(f"  rate limited (429), waiting {wait}s...")
                time.sleep(wait)
                continue
            r.raise_for_status()
            time.sleep(self.pause)
            return r.json()
        last.raise_for_status()

    def markets(self, ids, vs="usd"):
        """Current price + market cap + 24h/7d/30d change for a list of coin ids."""
        return self._get("/coins/markets", {
            "vs_currency": vs,
            "ids": ",".join(ids),
            "price_change_percentage": "24h,7d,30d",
            "per_page": len(ids),
            "page": 1,
        })

    def market_chart(self, coin_id, days=365, vs="usd"):
        """Historical price/volume/market-cap series. days>=90 returns daily points."""
        return self._get(f"/coins/{coin_id}/market_chart", {
            "vs_currency": vs,
            "days": days,
        })

    def ohlc(self, coin_id, days=365, vs="usd"):
        """OHLC candles. NOTE granularity: 1-2d=30min, 3-30d=4h, 31d+=4-day candles."""
        return self._get(f"/coins/{coin_id}/ohlc", {
            "vs_currency": vs,
            "days": days,
        })
