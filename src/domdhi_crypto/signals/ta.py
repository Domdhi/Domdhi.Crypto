"""Technical indicators, hand-rolled in pure pandas/numpy.

No pandas-ta dependency (it breaks on numpy 2.x / Python 3.13). Every function
takes a pandas Series of closes (or an OHLC DataFrame for atr) and returns a
Series so partial windows surface as NaN rather than silent garbage.

``analyze`` assumes its input is a *contiguous daily* close series; gap-filling
is the data layer's job (see ``db.load_close_series``), which keeps the math
here pure and reference-checkable.
"""
import numpy as np
import pandas as pd


def sma(close, period):
    """Simple moving average (rolling mean). Partial windows surface as NaN."""
    return close.rolling(period).mean()


def ema(close, span):
    """Exponential moving average, ``adjust=False`` recurrence (seeded on point 1)."""
    return close.ewm(span=span, adjust=False).mean()


def rsi(close, period=14):
    """Wilder's RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def macd(close, fast=12, slow=26, signal=9):
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def bollinger(close, period=20, mult=2):
    mid = sma(close, period)
    std = close.rolling(period).std()
    upper = mid + mult * std
    lower = mid - mult * std
    pctb = (close - lower) / (upper - lower)
    return mid, upper, lower, pctb


def atr(ohlc_df, period=14):
    """Average True Range from an OHLC DataFrame (high/low/close columns)."""
    high, low, close = ohlc_df["high"], ohlc_df["low"], ohlc_df["close"]
    prev = close.shift()
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def williams_r(ohlc_df, period=14):
    """Williams %R: where the close sits in the rolling high-low range, scaled to
    ``[-100, 0]``. ``%R = -100 * (HH - close) / (HH - LL)`` over ``period`` bars
    (HH = highest high, LL = lowest low). 0 = close at the period high, -100 = at
    the period low. NaN until the first full window."""
    high, low, close = ohlc_df["high"], ohlc_df["low"], ohlc_df["close"]
    hh = high.rolling(period).max()
    ll = low.rolling(period).min()
    rng = hh - ll
    return -100.0 * (hh - close) / rng.where(rng != 0)


def cci(ohlc_df, period=20):
    """Commodity Channel Index. ``CCI = (TP - SMA(TP)) / (0.015 * MAD(TP))`` where
    ``TP = (high + low + close) / 3`` (typical price) and MAD is the mean absolute
    deviation of TP about its rolling mean. The 0.015 constant scales ~70-80% of
    values into ``[-100, 100]`` (Lambert's original definition)."""
    tp = (ohlc_df["high"] + ohlc_df["low"] + ohlc_df["close"]) / 3.0
    sma_tp = tp.rolling(period).mean()
    mad = tp.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    return (tp - sma_tp) / (0.015 * mad.where(mad != 0))


def aroon(ohlc_df, period=25):
    """Aroon Up/Down: how recently the ``period``-window extreme occurred, scaled
    to ``[0, 100]``. Aroon Up = ``100 * (period - bars_since_highest_high) / period``
    (100 = a new high this bar, 0 = the high is ``period`` bars old); Aroon Down is
    the symmetric low measure. Returns ``(aroon_up, aroon_down)``. The rolling
    window spans ``period + 1`` bars (the current bar plus ``period`` priors), so a
    brand-new extreme scores 100."""
    win = int(period) + 1
    high, low = ohlc_df["high"], ohlc_df["low"]
    # argmax/argmin give the 0..period position of the extreme WITHIN the window;
    # position == period means the extreme is the most recent (current) bar.
    up = high.rolling(win).apply(lambda x: float(np.argmax(x)), raw=True)
    dn = low.rolling(win).apply(lambda x: float(np.argmin(x)), raw=True)
    aroon_up = 100.0 * up / period
    aroon_down = 100.0 * dn / period
    return aroon_up, aroon_down


def aroon_osc(ohlc_df, period=25):
    """Aroon Oscillator = Aroon Up - Aroon Down, range ``[-100, 100]``. Positive =
    a more-recent high than low (up-trend); negative = the reverse."""
    up, dn = aroon(ohlc_df, period)
    return up - dn


def adx(ohlc_df, period=14):
    """Average Directional Index (Wilder), range ``[0, 100]`` — trend STRENGTH,
    direction-agnostic. Built from the directional movement system:
    ``+DM/-DM`` (the larger of the up-move / down-move when it dominates), each
    Wilder-smoothed and divided by ATR to give ``+DI/-DI``; ``DX = 100 *
    |+DI - -DI| / (+DI + -DI)``; ADX is the Wilder-smoothed DX. Smoothing uses the
    same ``ewm(alpha=1/period, adjust=False)`` convention as ``atr`` for internal
    consistency. High ADX (>25) = strong trend regardless of sign."""
    high, low, close = ohlc_df["high"], ohlc_df["low"], ohlc_df["close"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=high.index
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=high.index
    )
    prev = close.shift()
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    alpha = 1.0 / period
    atr_ = tr.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    plus_di = 100.0 * plus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean() / atr_
    minus_di = 100.0 * minus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean() / atr_
    di_sum = (plus_di + minus_di).where((plus_di + minus_di) != 0)
    dx = 100.0 * (plus_di - minus_di).abs() / di_sum
    return dx.ewm(alpha=alpha, adjust=False, min_periods=period).mean()


def annualized_vol(close, periods_per_year=365):
    """Crypto trades 24/7 -> scale daily-return stdev by sqrt(365)."""
    return close.pct_change().std() * np.sqrt(periods_per_year)


def _f(x):
    """Coerce to a rounded float, mapping NaN/None to None for clean reporting."""
    if x is None:
        return None
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(xf) else round(xf, 6)


def analyze(close):
    """Latest indicator values + plain-language signals for a daily close series."""
    n = int(close.shape[0])
    line, sig, hist = macd(close)
    mid, upper, lower, pctb = bollinger(close)
    out = {
        "price": _f(close.iloc[-1]),
        "n_days": n,
        "rsi": _f(rsi(close).iloc[-1]),
        "macd": _f(line.iloc[-1]),
        "macd_signal": _f(sig.iloc[-1]),
        "macd_hist": _f(hist.iloc[-1]),
        "sma20": _f(sma(close, 20).iloc[-1]),
        "sma50": _f(sma(close, 50).iloc[-1]),
        "sma200": _f(sma(close, 200).iloc[-1]) if n >= 200 else None,
        "bb_upper": _f(upper.iloc[-1]),
        "bb_lower": _f(lower.iloc[-1]),
        "bb_pctb": _f(pctb.iloc[-1]),
        "volatility_annual": _f(annualized_vol(close)),
    }
    out["signals"] = _signals(out)
    return out


def _signals(o):
    sigs = []
    price = o["price"]
    rsi_v = o.get("rsi")
    if rsi_v is not None:
        if rsi_v >= 70:
            sigs.append(f"RSI {rsi_v:.0f} - overbought")
        elif rsi_v <= 30:
            sigs.append(f"RSI {rsi_v:.0f} - oversold")
        else:
            sigs.append(f"RSI {rsi_v:.0f} - neutral")
    h = o.get("macd_hist")
    if h is not None:
        sigs.append("MACD bullish (hist > 0)" if h > 0 else "MACD bearish (hist < 0)")
    s200 = o.get("sma200")
    if s200 is not None and price is not None:
        sigs.append("above 200D SMA (bull regime)" if price > s200
                    else "below 200D SMA (bear regime)")
    s50 = o.get("sma50")
    if s50 is not None and s200 is not None:
        sigs.append("golden cross (50D > 200D)" if s50 > s200
                    else "death cross (50D < 200D)")
    pctb = o.get("bb_pctb")
    if pctb is not None:
        if pctb > 1:
            sigs.append("stretched above upper Bollinger")
        elif pctb < 0:
            sigs.append("stretched below lower Bollinger")
    return sigs
