"""
src/ingestion/market_data.py
─────────────────────────────
Pulls peer company multiples and macro indicators via yfinance (free).
Used to build the comparable company (comps) table for GCash valuation.
"""

import logging
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# ── Peer Universe ────────────────────────────────────────────────────────────
# Mix of global digital payments / fintech peers and PSE-listed parents
PEER_TICKERS = {
    # Global digital payments benchmarks
    "SQ":   "Block Inc. (Cash App)",
    "PYPL":  "PayPal Holdings",
    "MA":    "Mastercard",
    "V":     "Visa",
    # SEA / APAC fintech proxies
    "SE":    "Sea Ltd (ShopeePay)",
    "2388.HK": "BOC Hong Kong (digital banking comps)",
    # PSE-listed parents / related companies
    "GLO.PS":  "Globe Telecom (GCash parent proxy)",
    "AC.PS":   "Ayala Corporation (co-investor)",
}

# ── Macro Indicators ─────────────────────────────────────────────────────────
MACRO_TICKERS = {
    "^VIX":  "CBOE Volatility Index",
    "^PSEI": "PSEi (Philippine Stock Exchange Index)",
    "^GSPC": "S&P 500",
    "^IXIC": "Nasdaq Composite",
}


def fetch_peer_info(tickers: dict | None = None) -> pd.DataFrame:
    """
    Fetch key valuation metrics for peer companies via yfinance.

    Returns a DataFrame with columns:
    ticker, name, market_cap, revenue_ttm, gross_profit_ttm,
    net_income_ttm, pe_ratio, ps_ratio, ev_revenue, gross_margin
    """
    if tickers is None:
        tickers = PEER_TICKERS

    rows = []
    for ticker, name in tickers.items():
        try:
            t = yf.Ticker(ticker)
            info = t.info

            market_cap    = info.get("marketCap", None)
            revenue_ttm   = info.get("totalRevenue", None)
            gross_profit  = info.get("grossProfits", None)
            net_income    = info.get("netIncomeToCommon", None)
            enterprise_v  = info.get("enterpriseValue", None)
            pe_ratio      = info.get("trailingPE", None)
            ps_ratio      = info.get("priceToSalesTrailing12Months", None)
            gross_margin  = info.get("grossMargins", None)

            ev_revenue = None
            if enterprise_v and revenue_ttm:
                ev_revenue = enterprise_v / revenue_ttm

            rows.append({
                "ticker":        ticker,
                "name":          name,
                "market_cap_bn": market_cap / 1e9 if market_cap else None,
                "revenue_ttm_bn": revenue_ttm / 1e9 if revenue_ttm else None,
                "gross_profit_bn": gross_profit / 1e9 if gross_profit else None,
                "net_income_bn": net_income / 1e9 if net_income else None,
                "ev_bn":         enterprise_v / 1e9 if enterprise_v else None,
                "pe_ratio":      pe_ratio,
                "ps_ratio":      ps_ratio,
                "ev_revenue":    ev_revenue,
                "gross_margin":  gross_margin,
            })
            logger.info("Fetched peer: %s (%s)", ticker, name)
        except Exception as e:
            logger.warning("Failed to fetch %s: %s", ticker, e)
            rows.append({"ticker": ticker, "name": name})

    return pd.DataFrame(rows)


def fetch_macro_data(days: int = 90) -> pd.DataFrame:
    """
    Fetch recent macro indicator data (VIX, PSEi, S&P500, Nasdaq).

    Returns a DataFrame of daily closing prices for each macro ticker.
    """
    end = datetime.today()
    start = end - timedelta(days=days)

    frames = {}
    for ticker, name in MACRO_TICKERS.items():
        try:
            data = yf.download(ticker, start=start, end=end, progress=False)
            if not data.empty:
                frames[ticker] = data["Close"].rename(name)
                logger.info("Fetched macro: %s — %d rows", ticker, len(data))
        except Exception as e:
            logger.warning("Failed to fetch macro %s: %s", ticker, e)

    if frames:
        return pd.DataFrame(frames).ffill()
    return pd.DataFrame()


def get_psex_30d_return() -> float | None:
    """
    Returns the PSEi 30-day trailing return as a decimal.
    e.g. 0.05 means +5% over last 30 days.
    """
    try:
        data = yf.download("^PSEI", period="35d", progress=False)
        if len(data) >= 2:
            price_now  = data["Close"].iloc[-1]
            price_30d  = data["Close"].iloc[0]
            return float((price_now - price_30d) / price_30d)
    except Exception as e:
        logger.warning("Could not compute PSEi 30d return: %s", e)
    return None


def get_vix_latest() -> float | None:
    """Returns the latest VIX closing value."""
    try:
        data = yf.download("^VIX", period="5d", progress=False)
        if not data.empty:
            return float(data["Close"].iloc[-1])
    except Exception as e:
        logger.warning("Could not fetch VIX: %s", e)
    return None


def compute_peer_medians(df: pd.DataFrame) -> dict:
    """
    Compute median multiples from the peer comps DataFrame.
    Returns dict of median EV/Revenue, P/S, P/E, and Gross Margin.
    """
    return {
        "median_ev_revenue":  df["ev_revenue"].median(),
        "median_ps_ratio":    df["ps_ratio"].median(),
        "median_pe_ratio":    df["pe_ratio"].median(),
        "median_gross_margin": df["gross_margin"].median(),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("\n=== Fetching Peer Comps ===")
    peers = fetch_peer_info()
    print(peers[["ticker", "name", "ev_revenue", "ps_ratio", "gross_margin"]].to_string(index=False))

    medians = compute_peer_medians(peers)
    print("\n=== Peer Median Multiples ===")
    for k, v in medians.items():
        print(f"  {k}: {v:.2f}" if v is not None else f"  {k}: N/A")

    print("\n=== Macro Snapshot ===")
    vix = get_vix_latest()
    psex = get_psex_30d_return()
    print(f"  VIX (latest):       {vix:.1f}" if vix else "  VIX: N/A")
    print(f"  PSEi 30d return:    {psex*100:+.1f}%" if psex else "  PSEi 30d: N/A")
