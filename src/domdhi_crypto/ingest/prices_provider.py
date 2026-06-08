"""PricesProvider — structural Protocol for the ingest data-source seam.

Any object whose method surface matches this Protocol is a valid provider;
no inheritance or import from this module is required (structural typing).
The factory ``get_provider`` returns a CoinGecko instance by default, using
a lazy import to avoid a circular dependency (coingecko.py must not import
this module).
"""
import typing


@typing.runtime_checkable
class PricesProvider(typing.Protocol):
    """Structural interface for a crypto price data source.

    Implementors do NOT need to inherit from this class — conformance is by
    shape (structural typing).  The three methods match the surface that
    ``cli.cmd_ingest`` consumes.
    """

    def markets(self, ids, vs="usd"):
        """Return current snapshot data for a list of coin ids."""
        ...

    def market_chart(self, coin_id, days=365, vs="usd"):
        """Return historical price/volume/market-cap series for one coin."""
        ...

    def ohlc(self, coin_id, days=365, vs="usd"):
        """Return OHLC candles for one coin."""
        ...


def get_provider() -> PricesProvider:
    """Return the default price data provider (CoinGecko).

    The import is lazy (inside this function) to prevent a circular dependency:
    coingecko.py must not import prices_provider, so prices_provider cannot be
    imported at module level in coingecko.py's namespace.
    """
    from domdhi_crypto.ingest.coingecko import CoinGecko  # noqa: PLC0415

    return CoinGecko()
