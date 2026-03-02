"""Price provider abstraction — yfinance (delayed) or IBKR (live)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from valuesentinel.config import get_config
from valuesentinel.data.yfinance_connector import fetch_live_price as yf_fetch_price
from valuesentinel.logging_config import get_logger

logger = get_logger("data.price")


class PriceProvider(ABC):
    """Abstract interface for fetching live/delayed prices."""

    @abstractmethod
    def get_price(self, symbol: str) -> float | None:
        ...

    @abstractmethod
    def is_realtime(self) -> bool:
        ...


class YFinancePriceProvider(PriceProvider):
    """Delayed quotes via yfinance (~15 min delay)."""

    def get_price(self, symbol: str) -> float | None:
        return yf_fetch_price(symbol)

    def is_realtime(self) -> bool:
        return False


class IBKRPriceProvider(PriceProvider):
    """Real-time quotes via Interactive Brokers ib_async."""

    def __init__(self) -> None:
        self._connected = False
        self._ib = None

    def connect(self) -> bool:
        try:
            from ib_async import IB  # type: ignore[import-untyped]

            cfg = get_config().ibkr
            self._ib = IB()
            self._ib.connect(cfg.host, cfg.port, clientId=cfg.client_id)
            self._connected = True
            logger.info("Connected to IBKR at %s:%d", cfg.host, cfg.port)
            return True
        except Exception as e:
            logger.warning("IBKR connection failed: %s — falling back to yfinance", e)
            self._connected = False
            return False

    def disconnect(self) -> None:
        if self._ib and self._connected:
            self._ib.disconnect()
            self._connected = False

    def get_price(self, symbol: str) -> float | None:
        if not self._connected or self._ib is None:
            return None
        try:
            from ib_async import Stock  # type: ignore[import-untyped]

            # Parse symbol — if it has a suffix like .L, try to map exchange
            base_symbol, exchange = _parse_ibkr_symbol(symbol)
            contract = Stock(base_symbol, exchange, "")
            self._ib.qualifyContracts(contract)
            ticker = self._ib.reqMktData(contract, "", False, False)
            self._ib.sleep(2)  # wait for data
            price = ticker.marketPrice()
            self._ib.cancelMktData(contract)
            if price and price > 0:
                return float(price)
            return None
        except Exception as e:
            logger.error("IBKR price fetch failed for %s: %s", symbol, e)
            return None

    def is_realtime(self) -> bool:
        return self._connected


def _parse_ibkr_symbol(symbol: str) -> tuple[str, str]:
    """Convert yfinance-style symbol to IBKR (base, exchange) tuple."""
    exchange_map = {
        ".L": "LSE",
        ".T": "TSE",
        ".NS": "NSE",
        ".HK": "SEHK",
        ".DE": "IBIS",
        ".PA": "SBF",
        ".AS": "AEB",
        ".MI": "BVME",
        ".TO": "TSE",
        ".AX": "ASX",
    }
    for suffix, exch in exchange_map.items():
        if symbol.endswith(suffix):
            return symbol[: -len(suffix)], exch
    # Default: assume US / SMART routing
    return symbol, "SMART"


class PriceProviderFactory:
    """Create the best available price provider."""

    _instance: PriceProvider | None = None

    @classmethod
    def get(cls) -> PriceProvider:
        if cls._instance is not None:
            return cls._instance

        # Try IBKR first
        ibkr = IBKRPriceProvider()
        if ibkr.connect():
            cls._instance = ibkr
            return cls._instance

        # Fallback to yfinance
        logger.info("Using yfinance delayed quotes for pricing")
        cls._instance = YFinancePriceProvider()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        if isinstance(cls._instance, IBKRPriceProvider):
            cls._instance.disconnect()
        cls._instance = None
