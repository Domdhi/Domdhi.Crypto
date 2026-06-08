"""Tests for the hand-rolled indicators.

The whole point of writing these by hand (ta.py's docstring) is auditability,
so this module pins the math: property checks for the easy invariants, plus
cross-checks against *independently coded* textbook reference implementations
of Wilder's RSI and EMA so a regression in the smoothing recurrence is caught.
"""
import numpy as np
import pandas as pd
import pytest

from domdhi_crypto.signals import ta

# ---- independent reference implementations (do NOT import from ta) ----

def wilder_rsi(closes, period=14):
    """Canonical Wilder RSI: SMA-seed the first average, then recursive smoothing."""
    d = np.diff(closes)
    gain = np.where(d > 0, d, 0.0)
    loss = np.where(d < 0, -d, 0.0)
    ag, al = gain[:period].mean(), loss[:period].mean()
    out = [np.nan] * period
    out.append(100 - 100 / (1 + (ag / al if al else np.inf)))
    for i in range(period, len(d)):
        ag = (ag * (period - 1) + gain[i]) / period
        al = (al * (period - 1) + loss[i]) / period
        out.append(100 - 100 / (1 + (ag / al if al else np.inf)))
    return np.array(out)


def ema(vals, span):
    """Plain EMA recurrence with adjust=False semantics, seeded on the first point."""
    alpha = 2 / (span + 1)
    out, prev = [], None
    for v in vals:
        prev = v if prev is None else alpha * v + (1 - alpha) * prev
        out.append(prev)
    return np.array(out)


# ---- RSI ----

def test_rsi_monotonic_uptrend_pegs_high():
    rsi = ta.rsi(pd.Series(np.arange(1, 60, dtype=float)))
    assert rsi.iloc[-1] == 100.0


def test_rsi_monotonic_downtrend_pegs_low():
    rsi = ta.rsi(pd.Series(np.arange(60, 1, -1, dtype=float)))
    assert rsi.iloc[-1] == 0.0


def test_rsi_balanced_chop_is_neutral():
    # Equal-sized ups and downs -> RSI hovers around the 50 midline.
    alt = pd.Series([100 + (i % 2) for i in range(80)], dtype=float)
    assert 45 <= ta.rsi(alt).iloc[-1] <= 55


def test_rsi_partial_window_is_nan():
    # Fewer than `period` changes -> no defined RSI yet.
    rsi = ta.rsi(pd.Series([10.0, 11.0, 12.0]))
    assert rsi.isna().all()
    # First defined value lands exactly at index == period.
    rsi14 = ta.rsi(pd.Series(np.linspace(10, 20, 40)))
    assert rsi14.iloc[:14].isna().all()
    assert not np.isnan(rsi14.iloc[14])


def test_rsi_converges_to_textbook_wilder():
    # ewm-seeding differs from SMA-seeding early but converges; pin that it does.
    vals = np.cumsum(np.sin(np.arange(400) / 7.0) + np.cos(np.arange(400) / 3.0)) + 100
    ours = ta.rsi(pd.Series(vals)).to_numpy()
    ref = wilder_rsi(vals.tolist())
    tail = slice(100, None)  # after warmup the two seedings agree
    assert np.nanmax(np.abs(ours[tail] - ref[tail])) < 0.05


# ---- MACD ----

def test_macd_matches_independent_ema_recurrence():
    vals = np.sin(np.arange(120) / 5.0) * 10 + 100
    line, sig, hist = ta.macd(pd.Series(vals))
    expected_line = ema(vals, 12) - ema(vals, 26)
    assert np.max(np.abs(line.to_numpy() - expected_line)) < 1e-9
    # Histogram is line minus signal, by definition.
    assert np.max(np.abs(hist.to_numpy() - (line - sig).to_numpy())) < 1e-12


def test_macd_flat_series_is_zero():
    line, sig, hist = ta.macd(pd.Series([50.0] * 60))
    assert abs(line.iloc[-1]) < 1e-9
    assert abs(hist.iloc[-1]) < 1e-9


# ---- Bollinger ----

def test_bollinger_pctb_above_one_when_price_spikes():
    base = [100.0] * 25
    spiked = pd.Series(base + [130.0])
    _, _, _, pctb = ta.bollinger(spiked)
    assert pctb.iloc[-1] > 1


# ---- OHLCV indicators (high/low) ----


def _ohlc(high, low, close):
    return pd.DataFrame(
        {"high": pd.Series(high, dtype=float),
         "low": pd.Series(low, dtype=float),
         "close": pd.Series(close, dtype=float)}
    )


def test_williams_r_matches_hand_calc_and_bounds():
    df = _ohlc([10, 11, 12, 13, 14], [8, 9, 9, 10, 11], [9, 10, 11, 12, 13])
    wr = ta.williams_r(df, 3)
    # idx4: HH([12,13,14])=14, LL([9,10,11])=9, close=13 -> -100*(14-13)/(14-9) = -20
    assert wr.iloc[4] == pytest.approx(-20.0)
    valid = wr.dropna()
    assert (valid <= 0).all() and (valid >= -100).all()
    assert wr.iloc[:2].isna().all()  # NaN until the first full window


def test_cci_matches_hand_calc():
    df = _ohlc([10, 11, 12, 13, 14], [8, 9, 9, 10, 11], [9, 10, 11, 12, 13])
    cci = ta.cci(df, 3)
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    win = tp.iloc[2:5]
    mad = (win - win.mean()).abs().mean()
    expected = (tp.iloc[4] - win.mean()) / (0.015 * mad)
    assert cci.iloc[4] == pytest.approx(expected)


def test_aroon_osc_pegs_high_on_pure_uptrend():
    n = 40
    df = _ohlc(np.arange(n) + 12.0, np.arange(n) + 10.0, np.arange(n) + 11.0)
    osc = ta.aroon_osc(df, 25)
    # every new bar is a fresh high (up=100) and the low is the oldest (down=0)
    assert osc.iloc[-1] == pytest.approx(100.0)
    valid = osc.dropna()
    assert (valid >= -100).all() and (valid <= 100).all()


def test_adx_is_bounded_and_high_in_strong_trend():
    n = 60
    up = _ohlc(np.arange(n) + 12.0, np.arange(n) + 10.0, np.arange(n) + 11.0)
    adx = ta.adx(up, 14)
    last = adx.dropna().iloc[-1]
    assert 0.0 <= last <= 100.0
    assert last > 25.0  # a clean monotonic trend is unambiguously "trending"


def test_adx_lower_in_chop_than_in_trend():
    n = 80
    trend = _ohlc(np.arange(n) + 12.0, np.arange(n) + 10.0, np.arange(n) + 11.0)
    chop_c = 100 + np.sin(np.arange(n))
    chop = _ohlc(chop_c + 1, chop_c - 1, chop_c)
    assert ta.adx(trend, 14).dropna().iloc[-1] > ta.adx(chop, 14).dropna().iloc[-1]


# ---- analyze() + signals ----

def test_analyze_golden_cross_and_bull_regime():
    up = pd.Series(np.linspace(10, 200, 260))
    sigs = ta.analyze(up)["signals"]
    assert any("golden cross" in s for s in sigs)
    assert any("bull regime" in s for s in sigs)


def test_analyze_death_cross_and_bear_regime():
    down = pd.Series(np.linspace(200, 10, 260))
    sigs = ta.analyze(down)["signals"]
    assert any("death cross" in s for s in sigs)
    assert any("bear regime" in s for s in sigs)


def test_analyze_sma200_none_for_short_series():
    out = ta.analyze(pd.Series(np.arange(1, 51, dtype=float)))
    assert out["sma200"] is None
    # ...and with no 200D SMA there is no cross/regime signal.
    assert not any("cross" in s or "regime" in s for s in out["signals"])


def test_analyze_nan_safe_outputs_are_none():
    # A 5-point series can't fill the 20/50/200 windows; those come back as None.
    out = ta.analyze(pd.Series([1.0, 2.0, 3.0, 2.0, 1.0]))
    assert out["sma50"] is None
    assert out["sma200"] is None
    assert out["price"] == 1.0
