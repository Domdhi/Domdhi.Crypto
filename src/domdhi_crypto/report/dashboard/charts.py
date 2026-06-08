import html
import json
import math
from pathlib import Path

import pandas as pd

from domdhi_crypto.signals import ta

from .theme import (
    BLUE,
    BORDER,
    GOLD,
    GREEN,
    MUTED,
    PURPLE,
    RED,
    TEXT,
)


def _fmt_money(x, d=2):
    return f"${x:,.{d}f}" if isinstance(x, (int, float)) else "n/a"


def _fmt_pct(x):
    return f"{x:+.1f}%" if isinstance(x, (int, float)) else "n/a"


def _clean(seq):
    return [v for v in seq if v is not None and v == v]  # drop None + NaN


def _esc(s):
    """HTML-escape a value for a text node (coin symbols/names come from the
    user-authored coins.local.json — escape so a pathological symbol can't inject
    markup into the offline dashboard)."""
    return html.escape(str(s))


def _esc_attr(s):
    """HTML-escape a value for an attribute context (e.g. a DOM id)."""
    return html.escape(str(s), quote=True)


def _poly(values, n, w, h, pad, vmin, vmax):
    """Map a value series to an SVG points string over n x-slots."""
    span = (vmax - vmin) or 1
    denom = (n - 1) or 1
    pts = []
    for i, v in enumerate(values):
        if v is None or v != v:
            continue
        x = pad + (w - 2 * pad) * (i / denom)
        y = h - pad - (h - 2 * pad) * ((v - vmin) / span)
        pts.append(f"{x:.1f},{y:.1f}")
    return " ".join(pts)


def _sparkline(values, w=130, h=34):
    vals = _clean(values)
    if len(vals) < 2:
        return ""
    vmin, vmax = min(vals), max(vals)
    pts = _poly(values, len(values), w, h, 2, vmin, vmax)
    color = GREEN if vals[-1] >= vals[0] else RED
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<polyline fill="none" stroke="{color}" stroke-width="1.5" points="{pts}"/></svg>')


def _price_chart(df, days=180, w=860, h=280, pad=40):
    close = df["close"]
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    view = df.index[-days:]
    c = list(close.reindex(view))
    s20 = list(sma20.reindex(view))
    s50 = list(sma50.reindex(view))
    s200 = list(sma200.reindex(view))
    n = len(view)
    pool = _clean(c + s20 + s50 + s200)
    if not pool:
        return ""
    vmin, vmax = min(pool), max(pool)
    rng = (vmax - vmin) or 1
    vmin -= rng * 0.05
    vmax += rng * 0.05

    def line(series, color, width=1.5, dash=""):
        pts = _poly(series, n, w, h, pad, vmin, vmax)
        if not pts:
            return ""
        da = f' stroke-dasharray="{dash}"' if dash else ""
        return f'<polyline fill="none" stroke="{color}" stroke-width="{width}"{da} points="{pts}"/>'

    # filled area under price
    cpts = _poly(c, n, w, h, pad, vmin, vmax)
    area = ""
    if cpts:
        first_x = cpts.split()[0].split(",")[0]
        last_x = cpts.split()[-1].split(",")[0]
        area = (f'<polygon fill="{BLUE}" fill-opacity="0.07" '
                f'points="{first_x},{h - pad} {cpts} {last_x},{h - pad}"/>')

    # y grid (vmin / mid / vmax)
    grid = ""
    for frac, val in ((0, vmin), (0.5, (vmin + vmax) / 2), (1, vmax)):
        y = h - pad - (h - 2 * pad) * frac
        grid += (f'<line x1="{pad}" y1="{y:.1f}" x2="{w - pad}" y2="{y:.1f}" '
                 f'stroke="{BORDER}" stroke-width="0.5"/>'
                 f'<text x="{pad - 6}" y="{y + 3:.1f}" fill="{MUTED}" font-size="10" '
                 f'text-anchor="end">{val:,.2f}</text>')

    d0 = view[0].strftime("%b %d")
    d1 = view[-1].strftime("%b %d")
    xlabels = (f'<text x="{pad}" y="{h - pad + 16}" fill="{MUTED}" font-size="10">{d0}</text>'
               f'<text x="{w - pad}" y="{h - pad + 16}" fill="{MUTED}" font-size="10" '
               f'text-anchor="end">{d1}</text>')

    return (f'<svg width="100%" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet">'
            f'{grid}{area}'
            f'{line(s200, PURPLE, 1.2, "4,3")}{line(s50, GOLD, 1.2, "4,3")}'
            f'{line(s20, BLUE, 1.2)}{line(c, TEXT, 1.8)}{xlabels}</svg>')


def _rsi_strip(df, days=180, w=860, h=80, pad=24):
    r = ta.rsi(df["close"]).reindex(df.index[-days:])
    n = len(r)
    pts = _poly(list(r), n, w, h, pad, 0, 100)
    if not pts:
        return ""
    bands = ""
    for lvl, col in ((70, RED), (30, GREEN)):
        y = h - pad - (h - 2 * pad) * (lvl / 100)
        bands += (f'<line x1="{pad}" y1="{y:.1f}" x2="{w - pad}" y2="{y:.1f}" '
                  f'stroke="{col}" stroke-width="0.5" stroke-dasharray="3,3"/>'
                  f'<text x="{pad - 4}" y="{y + 3:.1f}" fill="{MUTED}" font-size="9" '
                  f'text-anchor="end">{lvl}</text>')
    return (f'<svg width="100%" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet">'
            f'{bands}<polyline fill="none" stroke="{GOLD}" stroke-width="1.4" points="{pts}"/>'
            f'<text x="{pad}" y="14" fill="{MUTED}" font-size="10">RSI(14)</text></svg>')


def _pl_color(x):
    if not isinstance(x, (int, float)):
        return MUTED
    return GREEN if x >= 0 else RED


# --------------------------------------------------------------------------- #
# Vendored uPlot substrate (E18-S1, ADR-009)
#
# uPlot ships as a static asset committed under ``vendor/`` and inlined into the
# generated HTML at build time — never a CDN link, never a Python dependency
# (3-dep core preserved, ADR-007). See ``vendor/README.md`` for provenance.
# --------------------------------------------------------------------------- #

def _load_vendor(name):
    """Read a packaged vendored asset (``vendor/<name>``) as text.

    The asset lives inside this (``report``) slice, next to the module that inlines
    it — resolved package-relative via ``__file__``, never through ``shared.paths``."""
    return (Path(__file__).resolve().parent / "vendor" / name).read_text(encoding="utf-8")


def _json_script(obj):
    """``json.dumps`` hardened for embedding inside an inline ``<script>``.

    ``json.dumps`` does not escape ``/``, so a payload string containing the
    literal ``</script>`` would terminate the script element regardless of JSON
    quoting. Escape that sequence (and the U+2028/U+2029 line/paragraph
    separators that are valid JSON but illegal in JS string literals) so any
    user-authored coin symbol/label baked into a chart is inert. All panels that
    bake data into a ``<script>`` MUST route through this, not raw ``json.dumps``."""
    return (
        json.dumps(obj)
        .replace("</", "<\\/")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )


def _epoch_seconds(index):
    """Convert a pandas DatetimeIndex to a list of integer epoch seconds (uPlot's
    x-axis time base). Tz-naive timestamps are treated as UTC."""
    return [int(ts.timestamp()) for ts in pd.DatetimeIndex(index)]


def _uplot_chart(div_id, xs, series, *, height=260, time_axis=True):
    """Return a ``<div>`` + ``<script>`` that builds one interactive uPlot chart.

    Parameters
    ----------
    div_id:
        Unique DOM id for this chart's container. Key it off a unique value (coin
        ``id``, not the user-facing ``symbol`` — tickers can collide). It is
        escaped here for both the attribute and the JS lookup.
    xs:
        X values (epoch seconds when ``time_axis``, else plain numbers).

    ENCODING CONTRACT (panel authors, read this): this helper hardens everything
    it bakes into the ``<script>`` (data + div_id) via ``_json_script``. But any
    user-authored string YOU interpolate into HTML **body or attribute** context
    in your panel (coin symbol/name, factor name) MUST go through ``_esc`` /
    ``_esc_attr`` first — the script-payload hardening here does NOT cover your
    panel's own HTML. (This is the sink that produced code-review MAJOR-1.)
    series:
        List of ``{"name": str, "data": list[float|None], "color": str}`` dicts —
        one line per entry. ``None`` values render as gaps (uPlot-native).
    height:
        Chart height in px (width is responsive via the resize handler).
    time_axis:
        Whether the x-scale is a time scale (date-formatted ticks/cursor).

    The data + options are baked in via ``json.dumps`` (no live computation in the
    browser). uPlot provides zoom (drag-select), cursor, and tooltip natively, so
    the emitted chart is interactive with no extra wiring. The returned string is
    inserted as a value into ``_TEMPLATE`` — its ``{``/``}`` are NOT reprocessed by
    ``str.format`` (only the literal template's braces are)."""
    data = [list(xs)] + [list(s["data"]) for s in series]
    opts = {
        "width": 900,
        "height": height,
        "scales": {"x": {"time": bool(time_axis)}},
        "legend": {"show": True},
        "cursor": {"points": {"size": 6}},
        "axes": [
            {"stroke": MUTED, "grid": {"stroke": BORDER, "width": 0.5},
             "ticks": {"stroke": BORDER}},
            {"stroke": MUTED, "grid": {"stroke": BORDER, "width": 0.5},
             "ticks": {"stroke": BORDER}},
        ],
        "series": [{}] + [
            {"label": s["name"], "stroke": s.get("color", BLUE), "width": 1.6}
            for s in series
        ],
    }
    payload = _json_script({"data": data, "opts": opts})
    return (
        f'<div id="{_esc_attr(div_id)}" class="uchart"></div>'
        f"<script>(function(){{"
        f"var p={payload};"
        f"var el=document.getElementById({_json_script(div_id)});"
        f"function draw(){{el.innerHTML='';"
        f"p.opts.width=Math.max(320,el.clientWidth||900);"
        f"new uPlot(p.opts,p.data.map(function(a){{return a.slice();}}),el);}}"
        f"draw();window.addEventListener('resize',draw);"
        f"}})();</script>"
    )


def _panel(title, body):
    """Wrap panel body HTML in a titled card section (uniform panel chrome)."""
    if not body:
        return ""
    return (f'<div class="section-title">{title}</div>'
            f'<div class="panel card">{body}</div>')


def _fig(label, value, color=TEXT):
    """A single labelled figure (big number) for a panel's figure row."""
    return (f'<div class="fig"><div class="label">{label}</div>'
            f'<div class="val" style="color:{color}">{value}</div></div>')


def _finite(x):
    """True for a real, finite number (rejects None, bool, NaN, ±Infinity).

    The existing ``_fmt_money``/``_fmt_pct`` only reject non-numbers, so a float
    NaN slips through as ``"nan%"``. Risk/ledger functions return float NaN under
    window, so panels that surface them must finite-guard via this helper first."""
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _pct_or_na(frac, signed=True):
    """Render a fraction as a percentage, ``"n/a"`` when non-finite."""
    if not _finite(frac):
        return "n/a"
    return f"{frac * 100:+.1f}%" if signed else f"{frac * 100:.1f}%"


def _num_or_na(x, d=2):
    """Render a plain number to ``d`` decimals, ``"n/a"`` when non-finite."""
    return f"{x:.{d}f}" if _finite(x) else "n/a"


def _series_xy(series):
    """Split a dated ``pd.Series`` into (epoch-second xs, NaN->None ys) for uPlot,
    or ``(None, None)`` when there are fewer than 2 finite points to plot."""
    if series is None or len(series) < 2:
        return None, None
    xs = _epoch_seconds(series.index)
    ys = [float(v) if _finite(v) else None for v in series]
    return xs, ys
