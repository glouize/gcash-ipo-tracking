"""
src/ingestion/fx_rates.py
──────────────────────────
Fetches PHP/USD exchange rates from the BSP (Bangko Sentral ng Pilipinas)
Open Data API and yfinance as fallback.
"""

import logging
from datetime import datetime, timedelta
from functools import lru_cache

import requests
import yfinance as yf

logger = logging.getLogger(__name__)

BSP_FX_URL = "https://www.bsp.gov.ph/api/PhilippinePesoExchangeRate"


@lru_cache(maxsize=1)
def get_php_usd_rate(date_str: str | None = None) -> float:
    """
    Fetch the PHP/USD exchange rate for a given date (YYYY-MM-DD).
    Falls back to yfinance (PHPUSD=X) if BSP API is unavailable.

    Returns PHP per 1 USD (e.g., 56.25 means ₱56.25 = $1).
    """
    # Try BSP API first
    try:
        params = {"date": date_str or datetime.today().strftime("%Y-%m-%d")}
        resp = requests.get(BSP_FX_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # BSP returns a list; find USD row
        for entry in data.get("data", []):
            if entry.get("currency_code") == "USD":
                rate = float(entry.get("php_per_unit", 0))
                if rate > 0:
                    logger.info("BSP FX rate (PHP/USD): %.4f", rate)
                    return rate
    except Exception as e:
        logger.warning("BSP API unavailable: %s — falling back to yfinance", e)

    # Fallback: yfinance USDPHP=X ticker
    try:
        ticker = yf.Ticker("PHP=X")
        hist = ticker.history(period="5d")
        if not hist.empty:
            rate = float(hist["Close"].iloc[-1])
            logger.info("yfinance FX rate (PHP/USD): %.4f", rate)
            return rate
    except Exception as e:
        logger.warning("yfinance FX fallback failed: %s — using hardcoded rate", e)

    # Last resort: hardcoded approximate rate
    logger.warning("Using hardcoded PHP/USD fallback rate: 56.00")
    return 56.00


def php_to_usd(amount_php: float, rate: float | None = None) -> float:
    """Convert a PHP amount to USD."""
    if rate is None:
        rate = get_php_usd_rate()
    return amount_php / rate


def usd_to_php(amount_usd: float, rate: float | None = None) -> float:
    """Convert a USD amount to PHP."""
    if rate is None:
        rate = get_php_usd_rate()
    return amount_usd * rate


def format_php(amount: float, bn_threshold: float = 1e9) -> str:
    """Format a PHP amount with ₱ symbol and B/M suffix."""
    if abs(amount) >= bn_threshold:
        return f"₱{amount / 1e9:.2f}B"
    elif abs(amount) >= 1e6:
        return f"₱{amount / 1e6:.2f}M"
    return f"₱{amount:,.2f}"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    rate = get_php_usd_rate()
    print(f"Current PHP/USD rate: ₱{rate:.4f} per $1")
    print(f"GCash max market cap: {format_php(669e9)} = ${669e9 / rate / 1e9:.2f}B")
