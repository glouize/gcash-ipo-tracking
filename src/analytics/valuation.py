"""
src/analytics/valuation.py
────────────────────────────
5-method fair value triangulation for GCash (Mynt Inc.) IPO.
All values in Philippine Peso (₱) unless stated otherwise.
"""

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── GCash Financial Inputs ────────────────────────────────────────────────────
GCASH = {
    "revenue_2025_php_bn":     79.7,
    "net_income_2025_php_bn":  17.2,
    "net_margin_2025":         0.216,
    "revenue_h1_2026_php_bn":  43.3,
    "net_income_h1_2026_php_bn": 10.8,
    # Estimated NTM (Next Twelve Months) revenue — annualizing H1 2026 at ~10% growth
    "revenue_ntm_php_bn":      90.0,
    "gross_margin_est":        0.63,     # Estimated; company doesn't break out explicitly
    "total_shares_bn":         66.90,    # Fully diluted share count
    "final_offer_price_php":   6.60,     # Final IPO offer price set via bookbuilding (Oct 12, 2026)
    "listing_market_cap_php_bn": 441.54, # Actual market cap at ₱6.60 × 66.9B shares
    "max_price_php":           10.00,    # Administrative ceiling (not achieved)
    "analyst_mid_php":         7.50,     # Post-pricing analyst consensus midpoint (₱7.00–₱8.00)
    # Post-listing actuals (derived)
    "actual_pe_at_listing":    24.6,     # ₱441.5B / ₱17.95B NTM net income
    "actual_ev_rev_at_listing": 4.91,   # ₱441.5B / ₱90B NTM revenue
}

GCASH["gross_profit_ntm_php_bn"] = GCASH["revenue_ntm_php_bn"] * GCASH["gross_margin_est"]
GCASH["net_income_ntm_php_bn"]   = GCASH["revenue_ntm_php_bn"] * GCASH["net_margin_2025"]


@dataclass
class ValuationResult:
    method:    str
    ev_php_bn: float
    per_share_low:  float
    per_share_mid:  float
    per_share_high: float
    notes:     str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Method 1: Revenue Multiple (EV / NTM Revenue)
# ─────────────────────────────────────────────────────────────────────────────

def method_revenue_multiple(
    ntm_revenue_php_bn: float = GCASH["revenue_ntm_php_bn"],
    total_shares_bn: float    = GCASH["total_shares_bn"],
    peer_ev_revenue_multiple: float = 5.5,  # Median from SQ, PYPL, SE — updated from live comps
    em_discount: float = 0.20,              # 20% emerging market / low float discount
) -> ValuationResult:
    """EV = NTM Revenue × Multiple. Apply EM discount for PSE context."""
    mult_low  = peer_ev_revenue_multiple * (1 - em_discount) * 0.80
    mult_mid  = peer_ev_revenue_multiple * (1 - em_discount)
    mult_high = peer_ev_revenue_multiple * (1 - em_discount) * 1.20

    ev_low  = ntm_revenue_php_bn * mult_low
    ev_mid  = ntm_revenue_php_bn * mult_mid
    ev_high = ntm_revenue_php_bn * mult_high

    return ValuationResult(
        method="Revenue Multiple (EV/NTM Rev)",
        ev_php_bn=ev_mid,
        per_share_low  = ev_low  / total_shares_bn,
        per_share_mid  = ev_mid  / total_shares_bn,
        per_share_high = ev_high / total_shares_bn,
        notes=f"Peer EV/NTM Rev: {peer_ev_revenue_multiple}×, EM discount: {em_discount*100:.0f}%",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Method 2: Gross Profit Multiple (EV / Gross Profit)
# ─────────────────────────────────────────────────────────────────────────────

def method_gross_profit_multiple(
    gross_profit_php_bn: float = GCASH["gross_profit_ntm_php_bn"],
    total_shares_bn: float     = GCASH["total_shares_bn"],
    peer_ev_gp_multiple: float = 9.0,
    em_discount: float = 0.20,
) -> ValuationResult:
    mult_low  = peer_ev_gp_multiple * (1 - em_discount) * 0.85
    mult_mid  = peer_ev_gp_multiple * (1 - em_discount)
    mult_high = peer_ev_gp_multiple * (1 - em_discount) * 1.15

    ev_low  = gross_profit_php_bn * mult_low
    ev_mid  = gross_profit_php_bn * mult_mid
    ev_high = gross_profit_php_bn * mult_high

    return ValuationResult(
        method="Gross Profit Multiple (EV/GP)",
        ev_php_bn=ev_mid,
        per_share_low  = ev_low  / total_shares_bn,
        per_share_mid  = ev_mid  / total_shares_bn,
        per_share_high = ev_high / total_shares_bn,
        notes=f"Peer EV/GP: {peer_ev_gp_multiple}×, EM discount: {em_discount*100:.0f}%",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Method 3: P/E Multiple
# ─────────────────────────────────────────────────────────────────────────────

def method_pe_multiple(
    net_income_ntm_php_bn: float = GCASH["net_income_ntm_php_bn"],
    total_shares_bn: float       = GCASH["total_shares_bn"],
    peer_pe_multiple: float      = 28.0,
    em_discount: float           = 0.15,
) -> ValuationResult:
    pe_low  = peer_pe_multiple * (1 - em_discount) * 0.85
    pe_mid  = peer_pe_multiple * (1 - em_discount)
    pe_high = peer_pe_multiple * (1 - em_discount) * 1.15

    mkt_cap_low  = net_income_ntm_php_bn * pe_low
    mkt_cap_mid  = net_income_ntm_php_bn * pe_mid
    mkt_cap_high = net_income_ntm_php_bn * pe_high

    return ValuationResult(
        method="P/E Multiple",
        ev_php_bn=mkt_cap_mid,
        per_share_low  = mkt_cap_low  / total_shares_bn,
        per_share_mid  = mkt_cap_mid  / total_shares_bn,
        per_share_high = mkt_cap_high / total_shares_bn,
        notes=f"Peer P/E: {peer_pe_multiple}×, EM discount: {em_discount*100:.0f}%",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Method 4: Discounted Cash Flow (5-year)
# ─────────────────────────────────────────────────────────────────────────────

def method_dcf(
    base_revenue_php_bn: float = GCASH["revenue_ntm_php_bn"],
    net_margin: float          = GCASH["net_margin_2025"],
    total_shares_bn: float     = GCASH["total_shares_bn"],
    scenarios: dict | None     = None,
) -> ValuationResult:
    """
    Simple 5-year DCF with three scenarios (Bear, Base, Bull).
    Terminal value uses Gordon Growth Model.
    """
    if scenarios is None:
        scenarios = {
            "bear": {"growth_rates": [0.08, 0.08, 0.07, 0.06, 0.05], "wacc": 0.12, "tgr": 0.04},
            "base": {"growth_rates": [0.12, 0.15, 0.14, 0.12, 0.10], "wacc": 0.10, "tgr": 0.05},
            "bull": {"growth_rates": [0.18, 0.20, 0.18, 0.15, 0.12], "wacc": 0.09, "tgr": 0.06},
        }

    results = {}
    for scenario, params in scenarios.items():
        revenue = base_revenue_php_bn
        pv_fcf  = 0.0
        wacc    = params["wacc"]

        for i, g in enumerate(params["growth_rates"], start=1):
            revenue *= (1 + g)
            fcf      = revenue * net_margin
            pv_fcf  += fcf / ((1 + wacc) ** i)

        # Terminal value
        terminal_fcf = revenue * net_margin * (1 + params["tgr"])
        terminal_val = terminal_fcf / (wacc - params["tgr"])
        pv_terminal  = terminal_val / ((1 + wacc) ** 5)

        results[scenario] = (pv_fcf + pv_terminal)

    ev_low  = results["bear"]
    ev_mid  = results["base"]
    ev_high = results["bull"]

    return ValuationResult(
        method="DCF (5-Year)",
        ev_php_bn=ev_mid,
        per_share_low  = ev_low  / total_shares_bn,
        per_share_mid  = ev_mid  / total_shares_bn,
        per_share_high = ev_high / total_shares_bn,
        notes="Bear/Base/Bull scenarios; WACC 9–12%; TGR 4–6%",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Method 5: PSE Precedent Transactions
# ─────────────────────────────────────────────────────────────────────────────

# Largest PSE IPOs (public data) and their EV/Revenue at listing
PSE_PRECEDENTS = pd.DataFrame([
    {"company": "Monde Nissin (MONDE)", "year": 2021, "ev_revenue_at_listing": 7.2},
    {"company": "Converge (CNVRG)",     "year": 2020, "ev_revenue_at_listing": 5.8},
    {"company": "MREIT",                "year": 2021, "ev_revenue_at_listing": 6.1},
    {"company": "Citicore Energy REIT", "year": 2022, "ev_revenue_at_listing": 4.9},
    {"company": "Dito CME Holdings",    "year": 2020, "ev_revenue_at_listing": 3.2},
])

def method_precedent_transactions(
    ntm_revenue_php_bn: float = GCASH["revenue_ntm_php_bn"],
    total_shares_bn: float    = GCASH["total_shares_bn"],
) -> ValuationResult:
    median_mult = PSE_PRECEDENTS["ev_revenue_at_listing"].median()
    # GCash premium: profitable + growth story → +30% vs median PSE precedent
    mult_low  = median_mult * 0.85
    mult_mid  = median_mult * 1.30   # Premium for profitability + fintech category
    mult_high = median_mult * 1.60

    ev_low  = ntm_revenue_php_bn * mult_low
    ev_mid  = ntm_revenue_php_bn * mult_mid
    ev_high = ntm_revenue_php_bn * mult_high

    return ValuationResult(
        method="PSE Precedent Transactions",
        ev_php_bn=ev_mid,
        per_share_low  = ev_low  / total_shares_bn,
        per_share_mid  = ev_mid  / total_shares_bn,
        per_share_high = ev_high / total_shares_bn,
        notes=f"PSE precedent median EV/Rev: {median_mult:.1f}× (+30% fintech premium for base)",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Triangulation
# ─────────────────────────────────────────────────────────────────────────────

def run_all_methods(peer_ev_revenue: float = 5.5, peer_pe: float = 28.0) -> pd.DataFrame:
    """
    Run all 5 valuation methods and return a summary DataFrame.
    peer_ev_revenue and peer_pe should be updated from live market_data.py fetches.
    """
    methods = [
        method_revenue_multiple(peer_ev_revenue_multiple=peer_ev_revenue),
        method_gross_profit_multiple(),
        method_pe_multiple(peer_pe_multiple=peer_pe),
        method_dcf(),
        method_precedent_transactions(),
    ]

    rows = []
    for m in methods:
        rows.append({
            "Method":       m.method,
            "Low (₱)":     round(m.per_share_low, 2),
            "Mid (₱)":     round(m.per_share_mid, 2),
            "High (₱)":    round(m.per_share_high, 2),
            "Notes":        m.notes,
        })

    df = pd.DataFrame(rows)

    # Consensus row
    df.loc[len(df)] = {
        "Method":    "── CONSENSUS (median) ──",
        "Low (₱)":  round(df["Low (₱)"].median(), 2),
        "Mid (₱)":  round(df["Mid (₱)"].median(), 2),
        "High (₱)": round(df["High (₱)"].median(), 2),
        "Notes":    "Post-pricing analyst target: ₱7.00–₱8.00 | IPO priced at ₱6.60",
    }
    return df


if __name__ == "__main__":
    pd.set_option("display.max_colwidth", 60)
    result = run_all_methods()
    print("\n=== GCash (GCASH) — Fair Value Triangulation ===")
    print(result.to_string(index=False))
    print(f"\nMax offer price: ₱{GCASH['max_offer_price_php']:.2f}")
    print(f"Analyst consensus: ₱{GCASH['analyst_mid_php']:.2f}")
