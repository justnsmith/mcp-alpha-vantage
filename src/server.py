import logging
from datetime import datetime, timezone
from typing import Optional

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from client import AlphaVantageClient, AlphaVantageError, RateLimitError
from config import get_settings
from models import DailyPrices, ErrorResponse, HealthResponse, SymbolSearchResult
from models import TopPerformersResult, PerformerMetrics, MarketSummaryResult, MarketBreadth
from models import StockComparison, ScreenResult, PortfolioHolding, PortfolioSnapshot
from models import CompanyOverview, NewsSentimentResult, TechnicalIndicatorResult, EarningsResult

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Create FastMCP server
mcp = FastMCP("Alpha Vantage MCP Server")

# Initialize client
client = AlphaVantageClient()


def format_error(error: str, symbol: Optional[str] = None, query: Optional[str] = None) -> str:
    """Format an error response as JSON."""
    error_response = ErrorResponse(
        error=error,
        symbol=symbol,
        query=query,
        timestamp=datetime.now(timezone.utc),
    )
    return error_response.model_dump_json(indent=2)


@mcp.tool
async def get_stock_quote(symbol: str) -> str:
    """
    Get real-time stock quote for a symbol.

    Args:
        symbol: Stock ticker symbol (e.g., 'AAPL', 'MSFT', 'GOOGL')

    Returns:
        JSON string containing current price, volume, and other market data
    """
    try:
        logger.info(f"Fetching quote for {symbol}")
        quote = await client.get_quote(symbol)
        return quote.model_dump_json(indent=2)

    except RateLimitError as e:
        logger.warning(f"Rate limit reached: {e}")
        return format_error(f"Rate limit reached: {str(e)}", symbol=symbol)

    except AlphaVantageError as e:
        logger.error(f"Error fetching quote for {symbol}: {e}")
        return format_error(f"Error fetching quote: {str(e)}", symbol=symbol)

    except Exception as e:
        logger.exception(f"Unexpected error for {symbol}")
        return format_error(f"Unexpected error: {str(e)}", symbol=symbol)


@mcp.tool
async def get_daily_prices(symbol: str, outputsize: str = "compact") -> str:
    """
    Get daily historical prices for a stock.

    Args:
        symbol: Stock ticker symbol (e.g., 'AAPL', 'MSFT', 'GOOGL')
        outputsize: 'compact' returns last 100 days, 'full' returns 20+ years of data

    Returns:
        JSON string containing recent daily prices and total days available
    """
    try:
        logger.info(f"Fetching daily prices for {symbol} (outputsize={outputsize})")

        # Validate outputsize parameter
        if outputsize not in ["compact", "full"]:
            return format_error(
                "outputsize must be 'compact' or 'full'",
                symbol=symbol,
            )

        data = await client.get_daily_prices(symbol, outputsize)

        # Convert DailyPrice objects to dicts for JSON serialization
        recent_days_dict = {}
        for date, price in data["recent_days"].items():
            recent_days_dict[date] = price.model_dump(by_alias=True)

        result = DailyPrices(
            symbol=data["symbol"],
            recent_days=recent_days_dict,
            total_days_available=data["total_days_available"],
            retrieved_at=datetime.now(timezone.utc),
        )

        return result.model_dump_json(indent=2)

    except RateLimitError as e:
        logger.warning(f"Rate limit reached: {e}")
        return format_error(f"Rate limit reached: {str(e)}", symbol=symbol)

    except AlphaVantageError as e:
        logger.error(f"Error fetching daily prices for {symbol}: {e}")
        return format_error(f"Error fetching daily prices: {str(e)}", symbol=symbol)

    except Exception as e:
        logger.exception(f"Unexpected error for {symbol}")
        return format_error(f"Unexpected error: {str(e)}", symbol=symbol)


@mcp.tool
async def search_symbol(keywords: str) -> str:
    """
    Search for stock symbols by company name or keywords.

    Args:
        keywords: Company name or search keywords (e.g., 'Apple', 'Microsoft')

    Returns:
        JSON string containing matching symbols with company names, types, and regions
    """
    try:
        logger.info(f"Searching for symbols with keywords: {keywords}")
        matches = await client.search_symbols(keywords)

        result = SymbolSearchResult(
            query=keywords,
            matches=matches,
            count=len(matches),
            retrieved_at=datetime.now(timezone.utc),
        )

        return result.model_dump_json(indent=2)

    except RateLimitError as e:
        logger.warning(f"Rate limit reached: {e}")
        return format_error(f"Rate limit reached: {str(e)}", query=keywords)

    except AlphaVantageError as e:
        logger.error(f"Error searching for '{keywords}': {e}")
        return format_error(f"Error searching: {str(e)}", query=keywords)

    except Exception as e:
        logger.exception(f"Unexpected error searching for '{keywords}'")
        return format_error(f"Unexpected error: {str(e)}", query=keywords)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request):
    """Health check endpoint for monitoring server status."""
    try:
        # Try to get settings to verify configuration
        settings = get_settings()
        has_api_key = bool(settings.alpha_vantage_api_key)

        health = HealthResponse(
            status="healthy" if has_api_key else "degraded",
            service="Alpha Vantage MCP",
            timestamp=datetime.now(timezone.utc),
        )

        return JSONResponse(health.model_dump())

    except Exception as e:
        logger.exception("Health check failed")
        return JSONResponse(
            {"status": "unhealthy", "error": str(e)},
            status_code=500,
        )


@mcp.tool
async def analyze_top_performers(
    symbols: str, limit: int = 10, metric: str = "change_percent"
) -> str:
    """
    Analyze and rank stocks by performance metrics.

    Args:
        symbols: Comma-separated list of stock symbols (e.g., 'AAPL,MSFT,GOOGL,TSLA')
        limit: Number of top performers to return (default: 10)
        metric: Metric to rank by - 'change_percent' or 'volume' (default: 'change_percent')

    Returns:
        JSON string containing ranked top performers with their metrics
    """
    try:
        # Parse symbols
        symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]

        if not symbol_list:
            return format_error("No symbols provided")

        if len(symbol_list) > 50:
            return format_error("Maximum 50 symbols allowed to respect rate limits")

        # Validate metric
        if metric not in ["change_percent", "volume"]:
            return format_error("metric must be 'change_percent' or 'volume'")

        logger.info(f"Analyzing {len(symbol_list)} symbols for top performers by {metric}")

        # Fetch quotes for all symbols
        quotes = await client.get_batch_quotes(symbol_list)

        if not quotes:
            return format_error("Unable to fetch data for any of the provided symbols")

        # Convert to PerformerMetrics
        performers = []
        for quote in quotes:
            try:
                current_price = float(quote.price)
                previous_close = float(quote.previous_close)
                change = float(quote.change)
                volume = int(quote.volume)

                change_percent = (change / previous_close * 100) if previous_close > 0 else 0.0

                performers.append(
                    PerformerMetrics(
                        symbol=quote.symbol,
                        current_price=current_price,
                        previous_close=previous_close,
                        change=change,
                        change_percent=change_percent,
                        volume=volume,
                        period="1day",
                    )
                )
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse metrics for {quote.symbol}: {e}")
                continue

        if not performers:
            return format_error("Unable to calculate metrics for any stocks")

        # Sort by the requested metric
        if metric == "change_percent":
            performers.sort(key=lambda x: x.change_percent, reverse=True)
        else:  # volume
            performers.sort(key=lambda x: x.volume, reverse=True)

        # Limit results
        top_performers = performers[:limit]

        result = TopPerformersResult(
            period="1day",
            metric=metric,
            performers=top_performers,
            count=len(top_performers),
            analyzed_count=len(performers),
        )

        return result.model_dump_json(indent=2)

    except RateLimitError as e:
        logger.warning(f"Rate limit reached: {e}")
        return format_error(f"Rate limit reached: {str(e)}")

    except Exception as e:
        logger.exception("Unexpected error in analyze_top_performers")
        return format_error(f"Unexpected error: {str(e)}")


# Default benchmark symbols representing broad market exposure
_MARKET_BENCHMARKS = ["SPY", "QQQ", "DIA", "IWM", "VIX"]


@mcp.tool
async def get_market_summary(symbols: str = "") -> str:
    """
    Get a broad market summary using benchmark ETFs and/or custom symbols.

    Fetches quotes for SPY, QQQ, DIA, IWM, and VIX by default, then computes
    aggregate stats: average change, total volume, top gainer/loser, and
    advance/decline breadth.

    Args:
        symbols: Optional comma-separated list of additional symbols to include
                 (e.g., 'AAPL,TSLA'). Leave empty for benchmarks only.

    Returns:
        JSON string with per-symbol metrics plus aggregate market statistics.
    """
    try:
        # Build symbol list: benchmarks + any extras
        extra = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        symbol_list = list(dict.fromkeys(_MARKET_BENCHMARKS + extra))

        logger.info(f"Fetching market summary for {symbol_list}")
        quotes = await client.get_batch_quotes(symbol_list)

        if not quotes:
            return format_error("Unable to fetch data for any market symbols")

        # Build PerformerMetrics
        performers: list[PerformerMetrics] = []
        for quote in quotes:
            try:
                previous_close = float(quote.previous_close)
                change = float(quote.change)
                change_percent = (change / previous_close * 100) if previous_close > 0 else 0.0
                performers.append(
                    PerformerMetrics(
                        symbol=quote.symbol,
                        current_price=float(quote.price),
                        previous_close=previous_close,
                        change=change,
                        change_percent=change_percent,
                        volume=int(quote.volume),
                        period="1day",
                    )
                )
            except (ValueError, TypeError) as e:
                logger.warning(f"Skipping {quote.symbol} due to parse error: {e}")

        if not performers:
            return format_error("Unable to calculate metrics for any market symbols")

        # Aggregate stats
        avg_change = sum(p.change_percent for p in performers) / len(performers)
        total_volume = sum(p.volume for p in performers)

        sorted_by_change = sorted(performers, key=lambda x: x.change_percent)
        top_gainer = sorted_by_change[-1]
        top_loser = sorted_by_change[0]

        advancing = sum(1 for p in performers if p.change_percent > 0)
        declining = sum(1 for p in performers if p.change_percent < 0)
        unchanged = len(performers) - advancing - declining
        ad_ratio = (advancing / declining) if declining > 0 else None

        result = MarketSummaryResult(
            symbols_requested=symbol_list,
            symbols_retrieved=len(performers),
            average_change_percent=round(avg_change, 4),
            total_volume=total_volume,
            top_gainer=top_gainer,
            top_loser=top_loser,
            breadth=MarketBreadth(
                advancing=advancing,
                declining=declining,
                unchanged=unchanged,
                advance_decline_ratio=round(ad_ratio, 2) if ad_ratio is not None else None,
            ),
            quotes=performers,
        )

        return result.model_dump_json(indent=2)

    except RateLimitError as e:
        logger.warning(f"Rate limit reached: {e}")
        return format_error(f"Rate limit reached: {str(e)}")

    except Exception as e:
        logger.exception("Unexpected error in get_market_summary")
        return format_error(f"Unexpected error: {str(e)}")


@mcp.tool
async def compare_stocks(symbols: str) -> str:
    """
    Compare multiple stocks side-by-side with performance highlights.

    Fetches current quotes for all provided symbols and returns them in a
    unified view, calling out the highest gainer, biggest loser, highest
    volume, and most intraday-volatile stock.

    Args:
        symbols: Comma-separated list of stock symbols (e.g., 'AAPL,MSFT,GOOGL,TSLA')

    Returns:
        JSON string with per-stock metrics and highlighted comparisons
    """
    try:
        symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]

        if not symbol_list:
            return format_error("No symbols provided")

        if len(symbol_list) > 50:
            return format_error("Maximum 50 symbols allowed to respect rate limits")

        logger.info(f"Comparing {len(symbol_list)} symbols")
        raw_quotes = await client.get_batch_quotes(symbol_list)

        if not raw_quotes:
            return format_error("Unable to fetch data for any of the provided symbols")

        performers: list[PerformerMetrics] = []
        for quote in raw_quotes:
            try:
                previous_close = float(quote.previous_close)
                change = float(quote.change)
                change_percent = (change / previous_close * 100) if previous_close > 0 else 0.0
                high = float(quote.high)
                low = float(quote.low)
                intraday_range_pct = (
                    ((high - low) / previous_close * 100) if previous_close > 0 else None
                )
                performers.append(
                    PerformerMetrics(
                        symbol=quote.symbol,
                        current_price=float(quote.price),
                        previous_close=previous_close,
                        change=change,
                        change_percent=change_percent,
                        volume=int(quote.volume),
                        period="1day",
                        intraday_range_percent=(
                            round(intraday_range_pct, 4) if intraday_range_pct is not None else None
                        ),
                    )
                )
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse metrics for {quote.symbol}: {e}")

        if not performers:
            return format_error("Unable to calculate metrics for any stocks")

        sorted_by_change = sorted(performers, key=lambda x: x.change_percent)
        sorted_by_volume = sorted(performers, key=lambda x: x.volume, reverse=True)
        sorted_by_range = [p for p in performers if p.intraday_range_percent is not None]
        sorted_by_range.sort(key=lambda x: x.intraday_range_percent, reverse=True)

        result = StockComparison(
            symbols=[p.symbol for p in performers],
            quotes=performers,
            highest_gainer=sorted_by_change[-1],
            biggest_loser=sorted_by_change[0],
            highest_volume=sorted_by_volume[0],
            most_volatile=sorted_by_range[0] if sorted_by_range else None,
        )

        return result.model_dump_json(indent=2)

    except RateLimitError as e:
        logger.warning(f"Rate limit reached: {e}")
        return format_error(f"Rate limit reached: {str(e)}")

    except Exception as e:
        logger.exception("Unexpected error in compare_stocks")
        return format_error(f"Unexpected error: {str(e)}")


@mcp.tool
async def screen_stocks(
    symbols: str,
    min_change_percent: Optional[float] = None,
    max_change_percent: Optional[float] = None,
    min_volume: Optional[int] = None,
    direction: str = "any",
) -> str:
    """
    Screen a list of stocks by configurable criteria.

    Fetches current quotes and filters to only the symbols that meet all
    supplied thresholds. Useful for quick discovery of movers, high-volume
    names, or pure gainers/losers within a watchlist.

    Args:
        symbols: Comma-separated list of stock symbols to screen
        min_change_percent: Only include stocks with change% >= this value (e.g., 1.5)
        max_change_percent: Only include stocks with change% <= this value (e.g., -1.0)
        min_volume: Only include stocks with volume >= this value (e.g., 1000000)
        direction: 'gainers' (change > 0), 'losers' (change < 0), or 'any' (default)

    Returns:
        JSON string with the matching stocks and a summary of criteria applied
    """
    try:
        symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]

        if not symbol_list:
            return format_error("No symbols provided")

        if len(symbol_list) > 50:
            return format_error("Maximum 50 symbols allowed to respect rate limits")

        if direction not in ("gainers", "losers", "any"):
            return format_error("direction must be 'gainers', 'losers', or 'any'")

        logger.info(f"Screening {len(symbol_list)} symbols")
        raw_quotes = await client.get_batch_quotes(symbol_list)

        if not raw_quotes:
            return format_error("Unable to fetch data for any of the provided symbols")

        performers: list[PerformerMetrics] = []
        for quote in raw_quotes:
            try:
                previous_close = float(quote.previous_close)
                change = float(quote.change)
                change_percent = (change / previous_close * 100) if previous_close > 0 else 0.0
                performers.append(
                    PerformerMetrics(
                        symbol=quote.symbol,
                        current_price=float(quote.price),
                        previous_close=previous_close,
                        change=change,
                        change_percent=change_percent,
                        volume=int(quote.volume),
                        period="1day",
                    )
                )
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse metrics for {quote.symbol}: {e}")

        # Apply filters
        criteria_parts: list[str] = []

        def passes(p: PerformerMetrics) -> bool:
            if direction == "gainers" and p.change_percent <= 0:
                return False
            if direction == "losers" and p.change_percent >= 0:
                return False
            if min_change_percent is not None and p.change_percent < min_change_percent:
                return False
            if max_change_percent is not None and p.change_percent > max_change_percent:
                return False
            if min_volume is not None and p.volume < min_volume:
                return False
            return True

        if direction != "any":
            criteria_parts.append(f"direction={direction}")
        if min_change_percent is not None:
            criteria_parts.append(f"change%>={min_change_percent}")
        if max_change_percent is not None:
            criteria_parts.append(f"change%<={max_change_percent}")
        if min_volume is not None:
            criteria_parts.append(f"volume>={min_volume}")

        matched = [p for p in performers if passes(p)]
        matched.sort(key=lambda x: x.change_percent, reverse=True)

        criteria_str = (
            ", ".join(criteria_parts) if criteria_parts else "none (all symbols returned)"
        )

        result = ScreenResult(
            criteria_applied=criteria_str,
            matched=matched,
            matched_count=len(matched),
            total_screened=len(performers),
        )

        return result.model_dump_json(indent=2)

    except RateLimitError as e:
        logger.warning(f"Rate limit reached: {e}")
        return format_error(f"Rate limit reached: {str(e)}")

    except Exception as e:
        logger.exception("Unexpected error in screen_stocks")
        return format_error(f"Unexpected error: {str(e)}")


@mcp.tool
async def get_portfolio_snapshot(holdings: str) -> str:
    """
    Get a real-time snapshot of a stock portfolio with daily P&L.

    Accepts holdings as a comma-separated list of SYMBOL:shares pairs,
    fetches current quotes, and computes per-position market values and
    daily profit/loss, plus portfolio-level totals.

    Args:
        holdings: Comma-separated SYMBOL:shares pairs
                  (e.g., 'AAPL:10,MSFT:5,GOOGL:2')

    Returns:
        JSON string with per-holding metrics, total market value, and daily P&L
    """
    try:
        # Parse holdings string
        holding_map: dict[str, float] = {}
        for part in holdings.split(","):
            part = part.strip()
            if not part:
                continue
            if ":" not in part:
                return format_error(
                    f"Invalid holdings format '{part}'. Use SYMBOL:shares (e.g., AAPL:10)"
                )
            symbol_raw, shares_raw = part.split(":", 1)
            symbol = symbol_raw.strip().upper()
            try:
                shares = float(shares_raw.strip())
            except ValueError:
                return format_error(f"Invalid share count '{shares_raw}' for {symbol}")
            if shares <= 0:
                return format_error(f"Share count must be positive for {symbol}")
            holding_map[symbol] = shares

        if not holding_map:
            return format_error("No valid holdings provided")

        if len(holding_map) > 50:
            return format_error("Maximum 50 symbols allowed to respect rate limits")

        logger.info(f"Fetching portfolio snapshot for {list(holding_map.keys())}")
        raw_quotes = await client.get_batch_quotes(list(holding_map.keys()))

        if not raw_quotes:
            return format_error("Unable to fetch quotes for portfolio symbols")

        portfolio_holdings: list[PortfolioHolding] = []
        for quote in raw_quotes:
            shares = holding_map.get(quote.symbol, 0.0)
            try:
                current_price = float(quote.price)
                previous_close = float(quote.previous_close)
                change = float(quote.change)
                change_percent = (change / previous_close * 100) if previous_close > 0 else 0.0
                market_value = current_price * shares
                daily_pnl = change * shares

                portfolio_holdings.append(
                    PortfolioHolding(
                        symbol=quote.symbol,
                        shares=shares,
                        current_price=current_price,
                        market_value=round(market_value, 2),
                        change=change,
                        change_percent=round(change_percent, 4),
                        daily_pnl=round(daily_pnl, 2),
                    )
                )
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse holding for {quote.symbol}: {e}")

        if not portfolio_holdings:
            return format_error("Unable to calculate metrics for any portfolio holdings")

        total_market_value = sum(h.market_value for h in portfolio_holdings)
        total_daily_pnl = sum(h.daily_pnl for h in portfolio_holdings)
        prior_total_value = total_market_value - total_daily_pnl
        total_daily_pnl_percent = (
            (total_daily_pnl / prior_total_value * 100) if prior_total_value > 0 else 0.0
        )

        sorted_by_pnl = sorted(portfolio_holdings, key=lambda h: h.daily_pnl)

        result = PortfolioSnapshot(
            total_market_value=round(total_market_value, 2),
            total_daily_pnl=round(total_daily_pnl, 2),
            total_daily_pnl_percent=round(total_daily_pnl_percent, 4),
            holdings=portfolio_holdings,
            top_contributor=sorted_by_pnl[-1],
            top_detractor=sorted_by_pnl[0],
        )

        return result.model_dump_json(indent=2)

    except RateLimitError as e:
        logger.warning(f"Rate limit reached: {e}")
        return format_error(f"Rate limit reached: {str(e)}")

    except Exception as e:
        logger.exception("Unexpected error in get_portfolio_snapshot")
        return format_error(f"Unexpected error: {str(e)}")


@mcp.tool
async def get_company_overview(symbol: str) -> str:
    """
    Get company fundamentals and key metrics for a stock.

    Returns sector, industry, market cap, P/E ratio, EPS, beta, 52-week
    high/low, moving averages, analyst target price, and more.

    Args:
        symbol: Stock ticker symbol (e.g., 'AAPL', 'MSFT')

    Returns:
        JSON string with company fundamentals and valuation metrics
    """
    try:
        logger.info(f"Fetching company overview for {symbol}")
        overview = await client.get_company_overview(symbol)
        return overview.model_dump_json(indent=2)

    except RateLimitError as e:
        logger.warning(f"Rate limit reached: {e}")
        return format_error(f"Rate limit reached: {str(e)}", symbol=symbol)

    except AlphaVantageError as e:
        logger.error(f"Error fetching overview for {symbol}: {e}")
        return format_error(f"Error fetching overview: {str(e)}", symbol=symbol)

    except Exception as e:
        logger.exception(f"Unexpected error for {symbol}")
        return format_error(f"Unexpected error: {str(e)}", symbol=symbol)


@mcp.tool
async def get_technical_indicator(
    symbol: str,
    indicator: str,
    interval: str = "daily",
    time_period: int = 14,
) -> str:
    """
    Get technical indicator data for a stock.

    Supported indicators:
    - RSI: Relative Strength Index. Values above 70 suggest overbought,
      below 30 oversold. Uses time_period.
    - MACD: Moving Average Convergence Divergence. Returns MACD line,
      signal line, and histogram. time_period is ignored.
    - BBANDS: Bollinger Bands. Returns upper, middle, and lower bands.
      Uses time_period.

    Args:
        symbol: Stock ticker symbol (e.g., 'AAPL')
        indicator: One of 'RSI', 'MACD', 'BBANDS'
        interval: 'daily', 'weekly', or 'monthly' (default: 'daily')
        time_period: Lookback window for RSI/BBANDS (default: 14, ignored for MACD)

    Returns:
        JSON string with the 10 most recent data points
    """
    try:
        logger.info(f"Fetching {indicator} for {symbol} ({interval}, period={time_period})")
        result = await client.get_technical_indicator(symbol, indicator, interval, time_period)
        return result.model_dump_json(indent=2)

    except RateLimitError as e:
        logger.warning(f"Rate limit reached: {e}")
        return format_error(f"Rate limit reached: {str(e)}", symbol=symbol)

    except AlphaVantageError as e:
        logger.error(f"Error fetching {indicator} for {symbol}: {e}")
        return format_error(f"Error fetching indicator: {str(e)}", symbol=symbol)

    except Exception as e:
        logger.exception(f"Unexpected error for {symbol}")
        return format_error(f"Unexpected error: {str(e)}", symbol=symbol)


@mcp.tool
async def get_news_sentiment(
    tickers: str = "",
    topics: str = "",
    limit: int = 10,
) -> str:
    """
    Get recent news articles with sentiment scores.

    Fetches news from Alpha Vantage and returns per-article sentiment
    (Bullish / Somewhat-Bullish / Neutral / Somewhat-Bearish / Bearish)
    plus per-ticker relevance and sentiment within each article.

    At least one of tickers or topics should be provided for focused results.
    If both are empty, returns general market news.

    Args:
        tickers: Comma-separated ticker symbols to filter news (e.g., 'AAPL,MSFT')
        topics: Comma-separated topics (e.g., 'technology,earnings,ipo,mergers_and_acquisitions')
        limit: Number of articles to return, 1-50 (default: 10)

    Returns:
        JSON string with articles, sentiment scores, and ticker relevance
    """
    try:
        logger.info(f"Fetching news sentiment (tickers={tickers}, topics={topics}, limit={limit})")
        result = await client.get_news_sentiment(tickers, topics, limit)
        return result.model_dump_json(indent=2)

    except RateLimitError as e:
        logger.warning(f"Rate limit reached: {e}")
        return format_error(f"Rate limit reached: {str(e)}")

    except AlphaVantageError as e:
        logger.error(f"Error fetching news sentiment: {e}")
        return format_error(f"Error fetching news: {str(e)}")

    except Exception as e:
        logger.exception("Unexpected error in get_news_sentiment")
        return format_error(f"Unexpected error: {str(e)}")


@mcp.tool
async def get_earnings(symbol: str) -> str:
    """
    Get earnings history for a stock (last 8 quarters and 5 annual periods).

    Returns reported EPS, estimated EPS, earnings surprise, and surprise
    percentage for each quarter, plus annual EPS going back 5 years.

    Args:
        symbol: Stock ticker symbol (e.g., 'AAPL', 'MSFT')

    Returns:
        JSON string with quarterly and annual earnings history
    """
    try:
        logger.info(f"Fetching earnings for {symbol}")
        result = await client.get_earnings(symbol)
        return result.model_dump_json(indent=2)

    except RateLimitError as e:
        logger.warning(f"Rate limit reached: {e}")
        return format_error(f"Rate limit reached: {str(e)}", symbol=symbol)

    except AlphaVantageError as e:
        logger.error(f"Error fetching earnings for {symbol}: {e}")
        return format_error(f"Error fetching earnings: {str(e)}", symbol=symbol)

    except Exception as e:
        logger.exception(f"Unexpected error for {symbol}")
        return format_error(f"Unexpected error: {str(e)}", symbol=symbol)


# HTTP entrypoint
app = mcp.http_app()

# Stdio entrypoint
if __name__ == "__main__":
    try:
        logger.info("Starting Alpha Vantage MCP Server...")
        mcp.run()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception:
        logger.exception("Server failed to start")
        raise
