import logging
from typing import Any, Dict

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create a requests session with retry logic."""
        session = requests.Session()

        # Configure retries
        retry_strategy = Retry(
            total=self.settings.max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        return session

    def _make_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
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
        # Add API key to params
        params["apikey"] = self.settings.alpha_vantage_api_key

        try:
            logger.debug(f"Making request with params: {params}")
            response = self.session.get(
                self.settings.alpha_vantage_base_url,
                params=params,
                timeout=self.settings.request_timeout,
            )
            response.raise_for_status()
            data = response.json()

            # Check for API-specific errors
            if "Error Message" in data:
                raise AlphaVantageError(f"API Error: {data['Error Message']}")

            if "Note" in data:
                raise RateLimitError(f"Rate limit reached: {data['Note']}")

            return data

        except requests.exceptions.Timeout:
            raise AlphaVantageError("Request timed out")
        except requests.exceptions.RequestException as e:
            raise AlphaVantageError(f"Request failed: {str(e)}")

    def get_quote(self, symbol: str) -> StockQuote:
        """
        Get real-time stock quote.

        Args:
            symbol: Stock ticker symbol

        Returns:
            StockQuote object with current market data
        """
        params = {"function": "GLOBAL_QUOTE", "symbol": symbol.upper()}

        data = self._make_request(params)
        quote_data = data.get("Global Quote", {})

        if not quote_data:
            raise AlphaVantageError(f"No data found for symbol {symbol}")

        return StockQuote(
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

    def get_daily_prices(self, symbol: str, outputsize: str = "compact") -> Dict[str, Any]:
        """
        Get daily historical prices.

        Args:
            symbol: Stock ticker symbol
            outputsize: 'compact' (last 100 days) or 'full' (20+ years)

        Returns:
            Dictionary with recent days and metadata
        """
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol.upper(),
            "outputsize": outputsize,
        }

        data = self._make_request(params)
        time_series = data.get("Time Series (Daily)", {})

        if not time_series:
            raise AlphaVantageError(f"No daily data found for {symbol}")

        # Parse and sort dates
        parsed_series = {}
        for date, values in time_series.items():
            parsed_series[date] = DailyPrice(**values)

        # Get the 5 most recent days
        recent_dates = sorted(parsed_series.keys(), reverse=True)[:5]
        recent_data = {date: parsed_series[date] for date in recent_dates}

        return {
            "symbol": symbol.upper(),
            "recent_days": recent_data,
            "total_days_available": len(time_series),
        }

    def search_symbols(self, keywords: str) -> list[SymbolMatch]:
        """
        Search for stock symbols by keywords.

        Args:
            keywords: Search keywords (company name, etc.)

        Returns:
            List of matching symbols
        """
        params = {"function": "SYMBOL_SEARCH", "keywords": keywords}

        data = self._make_request(params)
        matches = data.get("bestMatches", [])

        if not matches:
            raise AlphaVantageError(f"No symbols found for '{keywords}'")

        # Parse matches
        results = []
        for match in matches[:10]:
            results.append(
                SymbolMatch(
                    symbol=match.get("1. symbol", ""),
                    name=match.get("2. name", ""),
                    type=match.get("3. type", ""),
                    region=match.get("4. region", ""),
                    currency=match.get("8. currency", ""),
                )
            )

        return results
