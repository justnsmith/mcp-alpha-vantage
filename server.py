import json
import os
from datetime import datetime, timezone
import requests
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

# Create FastMCP server
mcp = FastMCP("Alpha Vantage MCP Server")

# Alpha Vantage API configuration
BASE_URL = "https://www.alphavantage.co/query"


def get_api_key() -> str:
    """Get Alpha Vantage API key from environment"""
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        raise ValueError("ALPHA_VANTAGE_API_KEY environment variable is required")
    return api_key


def make_request(params: dict) -> dict:
    """Make API request to Alpha Vantage"""
    params["apikey"] = get_api_key()

    try:
        response = requests.get(BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Check for API errors
        if "Error Message" in data:
            raise ValueError(f"API Error: {data['Error Message']}")
        if "Note" in data:
            raise ValueError(f"Rate limit reached: {data['Note']}")

        return data
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Request failed: {str(e)}")


@mcp.tool
def get_stock_quote(symbol: str) -> str:
    """Get real-time stock quote for a symbol"""
    try:
        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": symbol.upper()
        }

        data = make_request(params)
        quote = data.get("Global Quote", {})

        if not quote:
            raise ValueError(f"No data found for symbol {symbol}")

        result = {
            "symbol": symbol.upper(),
            "price": quote.get("05. price", "N/A"),
            "change": quote.get("09. change", "N/A"),
            "change_percent": quote.get("10. change percent", "N/A"),
            "volume": quote.get("06. volume", "N/A"),
            "latest_trading_day": quote.get("07. latest trading day", "N/A"),
            "previous_close": quote.get("08. previous close", "N/A"),
            "open": quote.get("02. open", "N/A"),
            "high": quote.get("03. high", "N/A"),
            "low": quote.get("04. low", "N/A"),
            "retrieved_at": datetime.now(timezone.utc).isoformat()
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        error_result = {
            "error": f"Error fetching quote for {symbol}: {str(e)}",
            "symbol": symbol,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        return json.dumps(error_result, indent=2)


@mcp.tool
def get_daily_prices(symbol: str, outputsize: str = "compact") -> str:
    """
    Get daily historical prices for a stock

    Args:
        symbol: Stock ticker symbol
        outputsize: 'compact' (last 100 days) or 'full' (20+ years)
    """
    try:
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol.upper(),
            "outputsize": outputsize
        }

        data = make_request(params)
        time_series = data.get("Time Series (Daily)", {})

        if not time_series:
            raise ValueError(f"No daily data found for {symbol}")

        # Get the 5 most recent days
        recent_dates = sorted(time_series.keys(), reverse=True)[:5]
        recent_data = {date: time_series[date] for date in recent_dates}

        result = {
            "symbol": symbol.upper(),
            "recent_days": recent_data,
            "total_days_available": len(time_series),
            "retrieved_at": datetime.now(timezone.utc).isoformat()
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        error_result = {
            "error": f"Error fetching daily prices for {symbol}: {str(e)}",
            "symbol": symbol,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        return json.dumps(error_result, indent=2)


@mcp.tool
def search_symbol(keywords: str) -> str:
    """Search for stock symbols by company name or keywords"""
    try:
        params = {
            "function": "SYMBOL_SEARCH",
            "keywords": keywords
        }

        data = make_request(params)
        matches = data.get("bestMatches", [])

        if not matches:
            raise ValueError(f"No symbols found for '{keywords}'")

        # Format the results
        formatted_matches = []
        for match in matches[:10]:
            formatted_matches.append({
                "symbol": match.get("1. symbol", ""),
                "name": match.get("2. name", ""),
                "type": match.get("3. type", ""),
                "region": match.get("4. region", ""),
                "currency": match.get("8. currency", "")
            })

        result = {
            "query": keywords,
            "matches": formatted_matches,
            "count": len(formatted_matches),
            "retrieved_at": datetime.now(timezone.utc).isoformat()
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        error_result = {
            "error": f"Error searching for '{keywords}': {str(e)}",
            "query": keywords,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        return json.dumps(error_result, indent=2)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request):
    """Health check endpoint"""
    return JSONResponse({"status": "healthy", "service": "Alpha Vantage MCP"})


# HTTP entrypoint (deployment)
app = mcp.http_app()

# Stdio entrypoint (Claude Desktop / mpak)
if __name__ == "__main__":
    mcp.run()
