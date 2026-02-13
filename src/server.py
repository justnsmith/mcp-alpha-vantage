import logging
from datetime import datetime, timezone
from typing import Optional

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from client import AlphaVantageClient, AlphaVantageError, RateLimitError
from config import get_settings
from models import DailyPrices, ErrorResponse, HealthResponse, SymbolSearchResult
from models import TopPerformersResult, PerformerMetrics

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
def get_stock_quote(symbol: str) -> str:
    """
    Get real-time stock quote for a symbol.

    Args:
        symbol: Stock ticker symbol (e.g., 'AAPL', 'MSFT', 'GOOGL')

    Returns:
        JSON string containing current price, volume, and other market data
    """
    try:
        logger.info(f"Fetching quote for {symbol}")
        quote = client.get_quote(symbol)
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
def get_daily_prices(symbol: str, outputsize: str = "compact") -> str:
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

        data = client.get_daily_prices(symbol, outputsize)

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
def search_symbol(keywords: str) -> str:
    """
    Search for stock symbols by company name or keywords.

    Args:
        keywords: Company name or search keywords (e.g., 'Apple', 'Microsoft')

    Returns:
        JSON string containing matching symbols with company names, types, and regions
    """
    try:
        logger.info(f"Searching for symbols with keywords: {keywords}")
        matches = client.search_symbols(keywords)

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
def analyze_top_performers(
    symbols: str,
    limit: int = 10,
    metric: str = "change_percent"
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
        symbol_list = [s.strip().upper() for s in symbols.split(',') if s.strip()]

        if not symbol_list:
            return format_error("No symbols provided")

        if len(symbol_list) > 50:
            return format_error("Maximum 50 symbols allowed to respect rate limits")

        # Validate metric
        if metric not in ["change_percent", "volume"]:
            return format_error("metric must be 'change_percent' or 'volume'")

        logger.info(f"Analyzing {len(symbol_list)} symbols for top performers by {metric}")

        # Fetch quotes for all symbols
        quotes = client.get_batch_quotes(symbol_list)

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

                performers.append(PerformerMetrics(
                    symbol=quote.symbol,
                    current_price=current_price,
                    previous_close=previous_close,
                    change=change,
                    change_percent=change_percent,
                    volume=volume,
                    period="1day"
                ))
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
            analyzed_count=len(performers)
        )

        return result.model_dump_json(indent=2)

    except RateLimitError as e:
        logger.warning(f"Rate limit reached: {e}")
        return format_error(f"Rate limit reached: {str(e)}")

    except Exception as e:
        logger.exception("Unexpected error in analyze_top_performers")
        return format_error(f"Unexpected error: {str(e)}")

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
