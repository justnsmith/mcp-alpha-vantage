import asyncio
import logging
import threading
from typing import Any, Dict

import httpx
from cachetools import TTLCache
from cachetools.keys import hashkey

from config import get_settings
from models import DailyPrice, StockQuote, SymbolMatch

logger = logging.getLogger(__name__)


class AlphaVantageError(Exception):
    """Base exception for Alpha Vantage API errors."""

    pass


class RateLimitError(AlphaVantageError):
    """Rate limit exceeded error."""

    pass


class AlphaVantageClient:
    """Client for interacting with Alpha Vantage API."""

    def __init__(self):
        """Initialize the Alpha Vantage client."""
        self.settings = get_settings()
        self._http = httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(retries=self.settings.max_retries),
            timeout=self.settings.request_timeout,
        )
        self._lock = threading.Lock()
        self._quote_cache: TTLCache = TTLCache(maxsize=256, ttl=self.settings.cache_ttl_quote)
        self._daily_cache: TTLCache = TTLCache(maxsize=64, ttl=self.settings.cache_ttl_daily)
        self._search_cache: TTLCache = TTLCache(maxsize=128, ttl=self.settings.cache_ttl_search)

    async def _make_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make a request to the Alpha Vantage API.

        Args:
            params: Query parameters for the API request

        Returns:
            API response as dictionary

        Raises:
            RateLimitError: If rate limit is exceeded
            AlphaVantageError: For other API errors
        """
        params = {**params, "apikey": self.settings.alpha_vantage_api_key}

        try:
            logger.debug(f"Making request with params: {params}")
            response = await self._http.get(
                self.settings.alpha_vantage_base_url,
                params=params,
            )
            response.raise_for_status()
            data = response.json()

            if "Error Message" in data:
                raise AlphaVantageError(f"API Error: {data['Error Message']}")

            if "Note" in data:
                raise RateLimitError(f"Rate limit reached: {data['Note']}")

            return data

        except (AlphaVantageError, RateLimitError):
            raise
        except httpx.TimeoutException:
            raise AlphaVantageError("Request timed out")
        except httpx.HTTPStatusError as e:
            raise AlphaVantageError(f"HTTP error: {e.response.status_code}")
        except httpx.HTTPError as e:
            raise AlphaVantageError(f"Request failed: {str(e)}")

    async def get_quote(self, symbol: str) -> StockQuote:
        """
        Get real-time stock quote.

        Args:
            symbol: Stock ticker symbol

        Returns:
            StockQuote object with current market data
        """
        key = hashkey(symbol.upper())
        with self._lock:
            if key in self._quote_cache:
                logger.debug(f"Cache hit: quote {symbol}")
                return self._quote_cache[key]

        params = {"function": "GLOBAL_QUOTE", "symbol": symbol.upper()}
        data = await self._make_request(params)
        quote_data = data.get("Global Quote", {})

        if not quote_data:
            raise AlphaVantageError(f"No data found for symbol {symbol}")

        result = StockQuote(
            symbol=symbol.upper(),
            price=quote_data.get("05. price", "N/A"),
            change=quote_data.get("09. change", "N/A"),
            change_percent=quote_data.get("10. change percent", "N/A"),
            volume=quote_data.get("06. volume", "N/A"),
            latest_trading_day=quote_data.get("07. latest trading day", "N/A"),
            previous_close=quote_data.get("08. previous close", "N/A"),
            open=quote_data.get("02. open", "N/A"),
            high=quote_data.get("03. high", "N/A"),
            low=quote_data.get("04. low", "N/A"),
        )

        with self._lock:
            self._quote_cache[key] = result
        return result

    async def get_daily_prices(self, symbol: str, outputsize: str = "compact") -> Dict[str, Any]:
        """
        Get daily historical prices.

        Args:
            symbol: Stock ticker symbol
            outputsize: 'compact' (last 100 days) or 'full' (20+ years)

        Returns:
            Dictionary with recent days and metadata
        """
        key = hashkey(symbol.upper(), outputsize)
        with self._lock:
            if key in self._daily_cache:
                logger.debug(f"Cache hit: daily prices {symbol}")
                return self._daily_cache[key]

        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol.upper(),
            "outputsize": outputsize,
        }
        data = await self._make_request(params)
        time_series = data.get("Time Series (Daily)", {})

        if not time_series:
            raise AlphaVantageError(f"No daily data found for {symbol}")

        parsed_series = {date: DailyPrice(**values) for date, values in time_series.items()}
        recent_dates = sorted(parsed_series.keys(), reverse=True)[:5]
        result = {
            "symbol": symbol.upper(),
            "recent_days": {date: parsed_series[date] for date in recent_dates},
            "total_days_available": len(time_series),
        }

        with self._lock:
            self._daily_cache[key] = result
        return result

    async def search_symbols(self, keywords: str) -> list[SymbolMatch]:
        """
        Search for stock symbols by keywords.

        Args:
            keywords: Search keywords (company name, etc.)

        Returns:
            List of matching symbols
        """
        key = hashkey(keywords.lower())
        with self._lock:
            if key in self._search_cache:
                logger.debug(f"Cache hit: search '{keywords}'")
                return self._search_cache[key]

        params = {"function": "SYMBOL_SEARCH", "keywords": keywords}
        data = await self._make_request(params)
        matches = data.get("bestMatches", [])

        if not matches:
            raise AlphaVantageError(f"No symbols found for '{keywords}'")

        results = [
            SymbolMatch(
                symbol=m.get("1. symbol", ""),
                name=m.get("2. name", ""),
                type=m.get("3. type", ""),
                region=m.get("4. region", ""),
                currency=m.get("8. currency", ""),
            )
            for m in matches[:10]
        ]

        with self._lock:
            self._search_cache[key] = results
        return results

    async def get_batch_quotes(self, symbols: list[str]) -> list[StockQuote]:
        """
        Get quotes for multiple symbols concurrently.

        Args:
            symbols: List of stock ticker symbols

        Returns:
            List of StockQuote objects (failed symbols are skipped with a warning)
        """
        results = await asyncio.gather(
            *[self.get_quote(s) for s in symbols],
            return_exceptions=True,
        )
        quotes = []
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                logger.warning(f"Failed to get quote for {symbol}: {result}")
            else:
                quotes.append(result)
        return quotes
