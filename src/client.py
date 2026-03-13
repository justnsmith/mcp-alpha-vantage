import asyncio
import logging
import threading
from typing import Any, Dict

import httpx
from cachetools import TTLCache
from cachetools.keys import hashkey

from config import get_settings
from models import (
    AnnualEarning,
    CompanyOverview,
    DailyPrice,
    EarningsResult,
    IndicatorDataPoint,
    NewsArticle,
    NewsSentimentResult,
    QuarterlyEarning,
    StockQuote,
    SymbolMatch,
    TechnicalIndicatorResult,
    TickerSentiment,
)

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
        self._overview_cache: TTLCache = TTLCache(maxsize=128, ttl=self.settings.cache_ttl_overview)
        self._indicator_cache: TTLCache = TTLCache(maxsize=256, ttl=self.settings.cache_ttl_indicator)
        self._news_cache: TTLCache = TTLCache(maxsize=64, ttl=self.settings.cache_ttl_news)
        self._earnings_cache: TTLCache = TTLCache(maxsize=128, ttl=self.settings.cache_ttl_earnings)

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

    async def get_company_overview(self, symbol: str) -> CompanyOverview:
        """
        Get company fundamentals and key metrics.

        Args:
            symbol: Stock ticker symbol

        Returns:
            CompanyOverview with fundamentals, valuation ratios, and technical levels
        """
        key = hashkey(symbol.upper())
        with self._lock:
            if key in self._overview_cache:
                logger.debug(f"Cache hit: overview {symbol}")
                return self._overview_cache[key]

        params = {"function": "OVERVIEW", "symbol": symbol.upper()}
        data = await self._make_request(params)

        if not data or "Symbol" not in data:
            raise AlphaVantageError(f"No overview data found for symbol {symbol}")

        result = CompanyOverview(
            symbol=data.get("Symbol", symbol.upper()),
            name=data.get("Name", ""),
            description=data.get("Description", ""),
            exchange=data.get("Exchange", ""),
            currency=data.get("Currency", ""),
            country=data.get("Country", ""),
            sector=data.get("Sector", ""),
            industry=data.get("Industry", ""),
            market_cap=data.get("MarketCapitalization"),
            pe_ratio=data.get("PERatio"),
            peg_ratio=data.get("PEGRatio"),
            book_value=data.get("BookValue"),
            dividend_yield=data.get("DividendYield"),
            eps=data.get("EPS"),
            profit_margin=data.get("ProfitMargin"),
            return_on_equity=data.get("ReturnOnEquityTTM"),
            revenue_ttm=data.get("RevenueTTM"),
            beta=data.get("Beta"),
            week_52_high=data.get("52WeekHigh"),
            week_52_low=data.get("52WeekLow"),
            moving_avg_50=data.get("50DayMovingAverage"),
            moving_avg_200=data.get("200DayMovingAverage"),
            analyst_target_price=data.get("AnalystTargetPrice"),
            forward_pe=data.get("ForwardPE"),
            price_to_book=data.get("PriceToBookRatio"),
            ev_to_ebitda=data.get("EVToEBITDA"),
        )

        with self._lock:
            self._overview_cache[key] = result
        return result

    _SUPPORTED_INDICATORS = {"RSI", "MACD", "BBANDS"}

    async def get_technical_indicator(
        self,
        symbol: str,
        indicator: str,
        interval: str = "daily",
        time_period: int = 14,
    ) -> TechnicalIndicatorResult:
        """
        Get technical indicator data (RSI, MACD, or BBANDS).

        Args:
            symbol: Stock ticker symbol
            indicator: One of 'RSI', 'MACD', 'BBANDS'
            interval: 'daily', 'weekly', or 'monthly'
            time_period: Lookback window for RSI/BBANDS (ignored for MACD)

        Returns:
            TechnicalIndicatorResult with the 10 most recent data points
        """
        indicator = indicator.upper()
        if indicator not in self._SUPPORTED_INDICATORS:
            raise AlphaVantageError(
                f"Unsupported indicator '{indicator}'. Choose from: {', '.join(sorted(self._SUPPORTED_INDICATORS))}"
            )

        key = hashkey(symbol.upper(), indicator, interval, time_period)
        with self._lock:
            if key in self._indicator_cache:
                logger.debug(f"Cache hit: {indicator} {symbol}")
                return self._indicator_cache[key]

        params: Dict[str, Any] = {
            "function": indicator,
            "symbol": symbol.upper(),
            "interval": interval,
            "series_type": "close",
        }
        if indicator != "MACD":
            params["time_period"] = time_period

        data = await self._make_request(params)

        ta_key = f"Technical Analysis: {indicator}"
        time_series = data.get(ta_key, {})
        if not time_series:
            raise AlphaVantageError(f"No {indicator} data found for {symbol}")

        recent_dates = sorted(time_series.keys(), reverse=True)[:10]
        result = TechnicalIndicatorResult(
            symbol=symbol.upper(),
            indicator=indicator,
            interval=interval,
            time_period=time_period if indicator != "MACD" else None,
            recent_data=[
                IndicatorDataPoint(date=date, values=time_series[date])
                for date in recent_dates
            ],
        )

        with self._lock:
            self._indicator_cache[key] = result
        return result

    async def get_news_sentiment(
        self,
        tickers: str = "",
        topics: str = "",
        limit: int = 10,
    ) -> NewsSentimentResult:
        """
        Get news and sentiment data for tickers and/or topics.

        Args:
            tickers: Comma-separated ticker symbols (e.g., 'AAPL,MSFT')
            topics: Comma-separated topics (e.g., 'technology,earnings')
            limit: Max articles to return (1-50)

        Returns:
            NewsSentimentResult with articles and per-ticker sentiment scores
        """
        limit = max(1, min(50, limit))
        key = hashkey(tickers.upper(), topics.lower(), limit)
        with self._lock:
            if key in self._news_cache:
                logger.debug(f"Cache hit: news tickers={tickers} topics={topics}")
                return self._news_cache[key]

        params: Dict[str, Any] = {
            "function": "NEWS_SENTIMENT",
            "limit": limit,
            "sort": "LATEST",
        }
        if tickers:
            params["tickers"] = tickers.upper()
        if topics:
            params["topics"] = topics.lower()

        data = await self._make_request(params)
        feed = data.get("feed", [])

        articles = []
        for item in feed:
            ticker_sentiments = [
                TickerSentiment(
                    ticker=ts.get("ticker", ""),
                    relevance_score=ts.get("relevance_score", ""),
                    sentiment_score=ts.get("ticker_sentiment_score", ""),
                    sentiment_label=ts.get("ticker_sentiment_label", ""),
                )
                for ts in item.get("ticker_sentiment", [])
            ]
            articles.append(
                NewsArticle(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    time_published=item.get("time_published", ""),
                    source=item.get("source", ""),
                    summary=item.get("summary", ""),
                    overall_sentiment_score=float(item.get("overall_sentiment_score", 0)),
                    overall_sentiment_label=item.get("overall_sentiment_label", ""),
                    ticker_sentiment=ticker_sentiments,
                )
            )

        result = NewsSentimentResult(
            tickers=tickers or None,
            topics=topics or None,
            articles=articles,
            count=len(articles),
        )

        with self._lock:
            self._news_cache[key] = result
        return result

    async def get_earnings(self, symbol: str) -> EarningsResult:
        """
        Get earnings history (quarterly and annual).

        Args:
            symbol: Stock ticker symbol

        Returns:
            EarningsResult with recent quarterly and annual earnings
        """
        key = hashkey(symbol.upper())
        with self._lock:
            if key in self._earnings_cache:
                logger.debug(f"Cache hit: earnings {symbol}")
                return self._earnings_cache[key]

        params = {"function": "EARNINGS", "symbol": symbol.upper()}
        data = await self._make_request(params)

        if not data or "symbol" not in data:
            raise AlphaVantageError(f"No earnings data found for symbol {symbol}")

        annual = [
            AnnualEarning(
                fiscal_date_ending=e.get("fiscalDateEnding", ""),
                reported_eps=e.get("reportedEPS"),
            )
            for e in data.get("annualEarnings", [])[:5]
        ]

        quarterly = [
            QuarterlyEarning(
                fiscal_date_ending=e.get("fiscalDateEnding", ""),
                reported_date=e.get("reportedDate"),
                reported_eps=e.get("reportedEPS"),
                estimated_eps=e.get("estimatedEPS"),
                surprise=e.get("surprise"),
                surprise_percentage=e.get("surprisePercentage"),
            )
            for e in data.get("quarterlyEarnings", [])[:8]
        ]

        result = EarningsResult(
            symbol=data.get("symbol", symbol.upper()),
            annual_earnings=annual,
            quarterly_earnings=quarterly,
        )

        with self._lock:
            self._earnings_cache[key] = result
        return result

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
