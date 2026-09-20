"""
src/ingestion/pse_edge_scraper.py
──────────────────────────────────
Scrapes PSE EDGE (https://edge.pse.com.ph) for GCash / Mynt Inc. disclosures
and parses key financial metrics from their prospectus.
"""

import re
import time
import logging
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
PSE_EDGE_BASE = "https://edge.pse.com.ph"
COMPANY_CODE   = "GCASH"           # PSE ticker once listed; use Mynt pre-listing
MYNT_CIK       = "MYNT"           # PSE EDGE company search key
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ── GCash Prospectus Data (pre-seeded from public disclosures) ───────────────
GCASH_STATIC = {
    "company_name":        "Globe Fintech Innovations, Inc. (Mynt)",
    "ticker":              "GCASH",
    "exchange":            "Philippine Stock Exchange (PSE) — Main Board",
    "listing_date":        "2026-10-20",
    "offer_period_start":  "2026-10-06",
    "offer_period_end":    "2026-10-12",
    "max_offer_price_php": 10.00,
    "analyst_low_php":     7.50,
    "analyst_high_php":    8.50,
    "target_raise_php_bn": 92.32,
    "market_cap_php_bn":   669.0,
    "public_float_pct":    0.12,        # 12% (SEC granted exemption)
    "shares_offered_bn":   8.03,
    "overallotment_bn":    1.20,
    "lockup_days":         180,
    "lockup_expiry":       "2027-04-20",

    # Financials (from prospectus / public disclosures)
    "financials": {
        2023: {"revenue_php_bn": 33.5,  "net_income_php_bn": 7.0,  "net_margin": 0.209},
        2024: {"revenue_php_bn": 55.0,  "net_income_php_bn": 12.0, "net_margin": 0.218},
        2025: {"revenue_php_bn": 79.7,  "net_income_php_bn": 17.2, "net_margin": 0.216},
        "H1_2026": {"revenue_php_bn": 43.3, "net_income_php_bn": 10.8, "net_margin": 0.249},
    },

    # Share structure
    "primary_shares_bn":   1.61,
    "secondary_shares_bn": 6.42,
    "secondary_pct":       0.80,         # 80% of offering is secondary ⚠️

    # Cap table
    "shareholders": {
        "Globe Telecom":    0.45,
        "Ant Group":        0.33,
        "Ayala Corporation": 0.10,
        "MUFG Bank":        0.05,
        "Others / ESOP":    0.07,
    },

    # Operational metrics
    "mau_millions": 40.4,   # Monthly Active Users as of H1 2026

    # SEC / PSE regulatory milestones
    "sec_preeffective_date": "2026-09-05",
    "pse_approval_date":     "2026-09-17",
}


def get_gcash_static() -> dict:
    """Return the pre-seeded GCash IPO data from the prospectus."""
    return GCASH_STATIC.copy()


def fetch_pse_disclosures(company_query: str = "Mynt") -> list[dict]:
    """
    Fetch recent disclosures from PSE EDGE for a given company.

    Returns a list of disclosure dicts:
      [{"date": str, "title": str, "url": str, "type": str}, ...]
    """
    url = f"{PSE_EDGE_BASE}/companyPage.do?method=fetchHeaderData&company={company_query}"
    disclosures = []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # PSE EDGE disclosure rows are in a table with class "list-table"
        rows = soup.select("table.list-table tr")
        for row in rows[1:]:  # skip header
            cols = row.find_all("td")
            if len(cols) < 4:
                continue
            disclosures.append({
                "date":  cols[0].get_text(strip=True),
                "type":  cols[1].get_text(strip=True),
                "title": cols[2].get_text(strip=True),
                "url":   PSE_EDGE_BASE + cols[2].find("a", href=True)["href"]
                         if cols[2].find("a") else "",
            })
    except Exception as exc:
        logger.warning("PSE EDGE scrape failed (site may require JS): %s", exc)
        logger.info("Returning empty list — use static data instead.")

    return disclosures


def detect_price_range_changes(disclosures: list[dict]) -> list[dict]:
    """
    Filter disclosures for any amendments that mention price range changes.
    These are critical signals of book-building demand strength.
    """
    keywords = ["amended", "amendment", "price range", "offer price", "revised"]
    return [
        d for d in disclosures
        if any(kw in d["title"].lower() for kw in keywords)
    ]


def compute_revenue_growth(financials: dict) -> dict:
    """Compute YoY revenue growth rates from the financials dict."""
    years = sorted(k for k in financials if isinstance(k, int))
    growth = {}
    for i in range(1, len(years)):
        yr, prev = years[i], years[i - 1]
        rev_curr = financials[yr]["revenue_php_bn"]
        rev_prev = financials[prev]["revenue_php_bn"]
        growth[yr] = (rev_curr - rev_prev) / rev_prev
    return growth


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    data = get_gcash_static()
    growth = compute_revenue_growth(data["financials"])

    print("\n=== GCash IPO Core Data ===")
    print(f"Ticker:         {data['ticker']}")
    print(f"Listing Date:   {data['listing_date']}")
    print(f"Max Price:      ₱{data['max_offer_price_php']:.2f}")
    print(f"Analyst Range:  ₱{data['analyst_low_php']:.2f} – ₱{data['analyst_high_php']:.2f}")
    print(f"Target Raise:   ₱{data['target_raise_php_bn']:.1f}B")
    print(f"Market Cap:     ₱{data['market_cap_php_bn']:.0f}B")
    print(f"Public Float:   {data['public_float_pct']*100:.0f}%")

    print("\n=== Revenue Growth ===")
    for yr, g in growth.items():
        print(f"  {yr}: {g*100:+.1f}%")

    print("\n=== PSE EDGE Disclosures ===")
    disclosures = fetch_pse_disclosures()
    if disclosures:
        for d in disclosures[:5]:
            print(f"  [{d['date']}] {d['type']}: {d['title']}")
    else:
        print("  (PSE EDGE live scrape unavailable — using static data)")
