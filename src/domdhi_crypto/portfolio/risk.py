"""Portfolio-level risk metrics — pure leaf module (E16-S3).

All functions receive an open ``conn`` and a ``coins_cfg`` dict; they never
call ``db.connect()`` or load coins themselves.  The module imports only
numpy, pandas, stdlib math, and the first-party ``db`` module (ADR-001).

Public API
----------
correlation_matrix(conn, coins_cfg) -> pd.DataFrame
    Pairwise daily log-return correlations, indexed/columned by coin symbol.

portfolio_vol(conn, coins_cfg) -> float
    Annualised portfolio volatility (value-weighted), sqrt(365) convention.

beta_to_btc(conn, coins_cfg) -> dict[str, float]
    cov(asset, BTC) / var(BTC) for each non-stable coin.  Empty dict when no
    BTC benchmark is configured.

max_drawdown(series) -> float
    Worst peak-to-trough decline as a non-positive fraction.  Pure, no DB.
"""
import math

import numpy as np
import pandas as pd

from domdhi_crypto.shared import db

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _non_stable_coins(coins_cfg: dict) -> list[dict]:
    """Return the non-stable coin entries from *coins_cfg*."""
    return [c for c in coins_cfg.get("coins", []) if not c.get("stable", False)]


def _log_returns(conn, coin_id: str) -> pd.Series | None:
    """Load daily log returns for *coin_id*, or None if insufficient data."""
    df = db.load_close_series(conn, coin_id)
    if df is None:
        return None
    close = df["close"]
    ret = np.log(close / close.shift()).dropna()
    if ret.empty:
        return None
    return ret


def _aligned_returns(conn, coins: list[dict]) -> pd.DataFrame:
    """Build a symbol-keyed DataFrame of daily log returns, inner-joined on date.

    Columns are coin symbols.  Rows without a value for every coin are dropped
    (inner join), so downstream calculations see a rectangular matrix.
    """
    series: dict[str, pd.Series] = {}
    for c in coins:
        ret = _log_returns(conn, c["id"])
        if ret is not None:
            series[c["symbol"]] = ret
    if not series:
        return pd.DataFrame()
    frame = pd.DataFrame(series)
    return frame.dropna()


def _btc_coin(coins: list[dict]) -> dict | None:
    """Return the configured BTC benchmark entry, or None."""
    for c in coins:
        if c["id"].lower() == "bitcoin" or c["symbol"].upper() == "BTC":
            return c
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def correlation_matrix(conn, coins_cfg: dict) -> pd.DataFrame:
    """Pairwise daily log-return correlations for all non-stable configured coins.

    Returns a DataFrame whose index and columns are coin symbols (e.g. "BTC",
    "ETH").  Diagonal is 1.0; identical series produce off-diagonal == 1.0.

    Under-window behaviour: fewer than 2 non-stable coins or fewer than 2
    aligned return points yields a DataFrame whose values are NaN (or an empty
    DataFrame) rather than raising.
    """
    coins = _non_stable_coins(coins_cfg)
    if len(coins) < 2:
        return pd.DataFrame()

    aligned = _aligned_returns(conn, coins)
    if aligned.shape[0] < 2 or aligned.shape[1] < 2:
        # Build a NaN-filled frame with whatever symbols were loaded.
        syms = [c["symbol"] for c in coins]
        empty = pd.DataFrame(np.nan, index=syms, columns=syms)
        return empty

    return aligned.corr()


def portfolio_vol(conn, coins_cfg: dict) -> float:
    """Annualised portfolio volatility (value-weighted), sqrt(365) convention.

    Value share: value_i = amount_i * latest_price_i.  Latest price is taken
    from the most recent snapshot; falls back to the last close from
    ``db.load_close_series`` when no snapshot exists.

    Under-window: zero or one aligned return points → ``float('nan')``.
    """
    coins = _non_stable_coins(coins_cfg)
    if not coins:
        return float("nan")

    # Collect log-return series per coin and compute value weights.
    series_map: dict[str, pd.Series] = {}
    values: dict[str, float] = {}

    for c in coins:
        ret = _log_returns(conn, c["id"])
        if ret is None:
            continue

        # Latest price: snapshot first, then last close.
        price = db.latest_snapshot_price(conn, c["id"])
        if price is None:
            df = db.load_close_series(conn, c["id"])
            price = float(df["close"].iloc[-1]) if df is not None else None
        if price is None or not math.isfinite(price) or price <= 0:
            continue

        value = c.get("amount", 0.0) * price
        if not math.isfinite(value) or value <= 0:
            continue

        series_map[c["symbol"]] = ret
        values[c["symbol"]] = value

    if not series_map:
        return float("nan")

    # Align all series (inner join on date).
    frame = pd.DataFrame(series_map).dropna()
    if frame.shape[0] < 2:
        return float("nan")

    # Normalise weights.
    total = sum(values[sym] for sym in frame.columns)
    if not math.isfinite(total) or total <= 0:
        return float("nan")
    weights = np.array([values[sym] / total for sym in frame.columns])

    # Weighted portfolio daily return.
    port_ret = (frame.values * weights).sum(axis=1)
    port_std = float(np.std(port_ret, ddof=1))

    if not math.isfinite(port_std):
        return float("nan")

    return port_std * math.sqrt(365)


def beta_to_btc(conn, coins_cfg: dict) -> dict[str, float]:
    """cov(asset, BTC) / var(BTC) for each non-stable coin, keyed by symbol.

    Returns ``{}`` when no BTC benchmark is configured.  BTC's own entry is
    ≈ 1.0.  Coins with fewer than 2 aligned return points yield ``float('nan')``
    for their entry (or are omitted when there is no return data at all).
    """
    coins = _non_stable_coins(coins_cfg)
    btc_coin = _btc_coin(coins)
    if btc_coin is None:
        return {}

    btc_ret = _log_returns(conn, btc_coin["id"])
    if btc_ret is None:
        # BTC series empty — can't compute betas.
        return {}

    btc_var = float(btc_ret.var())
    if not math.isfinite(btc_var) or btc_var == 0.0:
        return {}

    result: dict[str, float] = {}
    for c in coins:
        asset_ret = _log_returns(conn, c["id"])
        if asset_ret is None:
            result[c["symbol"]] = float("nan")
            continue

        # Inner-join on date.
        aligned = pd.concat(
            {"asset": asset_ret, "btc": btc_ret}, axis=1
        ).dropna()

        if aligned.shape[0] < 2:
            result[c["symbol"]] = float("nan")
            continue

        cov = float(aligned["asset"].cov(aligned["btc"]))
        var_btc = float(aligned["btc"].var())

        if not math.isfinite(var_btc) or var_btc == 0.0:
            result[c["symbol"]] = float("nan")
        else:
            beta = cov / var_btc
            result[c["symbol"]] = float("nan") if not math.isfinite(beta) else beta

    return result


def max_drawdown(series) -> float:
    """Worst peak-to-trough decline as a non-positive fraction.

    Accepts any pandas Series or array-like of values.  Returns 0.0 for a
    monotonically rising series.  Does not access the database.

    Example: [100, 120, 90, 110, 80, 130] → -1/3  (peak 120 → trough 80).
    """
    s = pd.Series(series, dtype=float)
    if s.empty or len(s) < 2:
        return 0.0

    running_max = s.cummax()
    drawdowns = (s - running_max) / running_max
    worst = float(drawdowns.min())
    return worst if math.isfinite(worst) else 0.0
