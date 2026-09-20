"""
src/analytics/risk_flags.py
─────────────────────────────
Automated red flag scanner for the GCash IPO.
Pre-seeded with known risks from the prospectus; also runs dynamic checks.
"""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    CRITICAL = "🚨 Critical"
    WARNING  = "⚠️ Warning"
    OK       = "✅ Clear"
    INFO     = "ℹ️ Info"


@dataclass
class RiskFlag:
    id:          str
    name:        str
    severity:    Severity
    description: str
    detected:    bool = True
    detail:      str  = ""
    source:      str  = "Prospectus / Public Disclosure"


# ── Pre-Seeded GCash Risk Flags (from prospectus analysis) ───────────────────

GCASH_STATIC_FLAGS: list[RiskFlag] = [

    RiskFlag(
        id="F01",
        name="High Secondary Share Offering (80%)",
        severity=Severity.CRITICAL,
        description=(
            "80% of shares offered are secondary (existing shareholders selling). "
            "Only 20% are primary shares raising fresh capital for Mynt. "
            "This means ~₱73.9B of the ₱92.3B raise goes to Globe, Ant Group, "
            "Ayala, and MUFG — not to the company itself."
        ),
        detail="Secondary: 6.42B shares. Primary: 1.61B shares.",
        source="Prospectus — Share Offering Structure",
    ),

    RiskFlag(
        id="F02",
        name="Revenue Growth Deceleration",
        severity=Severity.CRITICAL,
        description=(
            "Revenue growth has decelerated sharply: 64% (2023→2024) → 45% (2024→2025) "
            "→ ~10% (H1 2026 YoY). The company is reaching saturation in its core "
            "Philippine market with 40.4M MAU in a ~70M internet-user country."
        ),
        detail="H1 2026 revenue: ₱43.3B vs H1 2025: ~₱39.4B (+10% YoY).",
        source="Prospectus — Financial Statements",
    ),

    RiskFlag(
        id="F03",
        name="Massive Lockup Overhang at D+180",
        severity=Severity.CRITICAL,
        description=(
            "Only 12% public float at listing. ~88% of fully-diluted shares are locked "
            "for 180 days. When lockup expires (Apr 20, 2027), major shareholders "
            "Globe Telecom, Ant Group, Ayala, and MUFG may sell large blocks. "
            "Lockup overhang ratio: ~7.3× public float."
        ),
        detail="Locked shares: ~58.9B. Public float: ~8.0B. Ratio: 7.3×.",
        source="Prospectus — Lockup Arrangements",
    ),

    RiskFlag(
        id="F04",
        name="Ant Group (Chinese Entity) as 33% Shareholder",
        severity=Severity.WARNING,
        description=(
            "Ant Group, an Alibaba affiliate subject to Chinese regulatory oversight, "
            "holds ~33% of Mynt. This creates regulatory scrutiny risk (US-China tensions, "
            "PDEA/NTC oversight in Philippines), potential forced divestiture scenarios, "
            "and sensitivity to Chinese market/regulatory events."
        ),
        detail="Ant Group stake: ~33%.",
        source="Prospectus — Principal Shareholders",
    ),

    RiskFlag(
        id="F05",
        name="Very Low Public Float (12% — SEC Exemption)",
        severity=Severity.WARNING,
        description=(
            "SEC granted an exemption from the standard 15% float requirement. "
            "A 12% float creates high price volatility risk (both upside Day-1 pop "
            "and sharp downside moves on low liquidity days). Institutional rebalancing "
            "orders can move the price significantly."
        ),
        detail="Float: 12% vs standard 15% requirement.",
        source="SEC Pre-Effective Letter, Sep 5, 2026",
    ),

    RiskFlag(
        id="F06",
        name="H1 2026 Net Income Declined vs H1 2025",
        severity=Severity.WARNING,
        description=(
            "H1 2026 net income was ₱10.8B — a slight decline compared to H1 2025. "
            "While net margin improved to ~25%, absolute profit growth has stalled. "
            "This may indicate increasing operating costs (lending provisions, expansion)."
        ),
        detail="H1 2026 NI: ₱10.8B vs H1 2025 est.: ~₱11.0B.",
        source="Prospectus — H1 2026 Unaudited Financials",
    ),

    RiskFlag(
        id="F07",
        name="Philippine Market Concentration",
        severity=Severity.WARNING,
        description=(
            "GCash operates almost exclusively in the Philippines. "
            "With ~40.4M MAU in a country of ~80M adults (~60M smartphone users), "
            "organic growth headroom is narrowing. International expansion (GCash Padala, "
            "remittance corridors) is early-stage and unproven at scale."
        ),
        detail="Revenue geography: ~100% Philippines.",
        source="Prospectus — Business Description",
    ),

    RiskFlag(
        id="F08",
        name="No Dual-Class Share Structure",
        severity=Severity.OK,
        detected=True,
        description="Standard single-class share structure. All shares have equal voting rights.",
        detail="Governance risk: None from share structure.",
        source="Prospectus",
    ),

    RiskFlag(
        id="F09",
        name="Profitable at IPO",
        severity=Severity.OK,
        detected=True,
        description=(
            "Unlike most high-profile tech IPOs, GCash is profitable (₱17.2B net income in 2025, "
            "~21.6% net margin). This reduces the primary valuation risk of 'loss-making growth story.'"
        ),
        detail="2025 net margin: 21.6%. ROE: 32.1%.",
        source="Prospectus",
    ),

    RiskFlag(
        id="F10",
        name="Largest PH IPO Ever — Price Discovery Risk",
        severity=Severity.INFO,
        description=(
            "At ₱669B market cap, GCash will be one of the top-5 largest PSE-listed companies "
            "from Day-1. There is limited comparable precedent for price discovery of a "
            "company this large on the PSE. Institutional demand from local funds may be "
            "insufficient to absorb selling pressure."
        ),
        detail="Target market cap: ₱669B (~US$10.8B).",
        source="Market Analysis",
    ),
]


def get_all_flags() -> list[RiskFlag]:
    """Return the full list of pre-seeded risk flags."""
    return GCASH_STATIC_FLAGS.copy()


def get_flags_by_severity(severity: Severity) -> list[RiskFlag]:
    """Filter flags by severity level."""
    return [f for f in GCASH_STATIC_FLAGS if f.severity == severity]


def compute_risk_score() -> dict:
    """
    Compute an overall risk score (0–100, higher = riskier).
    Weights: Critical=30pts, Warning=10pts, OK/Info=-5pts.
    """
    weights = {
        Severity.CRITICAL: 30,
        Severity.WARNING:  10,
        Severity.OK:      -5,
        Severity.INFO:     0,
    }
    score = 0
    breakdown = {s: 0 for s in Severity}

    for flag in GCASH_STATIC_FLAGS:
        if flag.detected:
            score += weights[flag.severity]
            breakdown[flag.severity] += 1

    score = max(0, min(100, score))

    return {
        "score":     score,
        "label":     "High Risk" if score >= 60 else ("Medium Risk" if score >= 30 else "Low Risk"),
        "breakdown": {k.value: v for k, v in breakdown.items()},
    }


def run_dynamic_checks(
    h1_revenue_growth_yoy: Optional[float] = 0.10,
    insider_sell_pct: Optional[float] = 0.80,
    float_pct: Optional[float] = 0.12,
) -> list[RiskFlag]:
    """
    Run parametric checks and return dynamically generated flags.
    These supplement the static pre-seeded flags.
    """
    dynamic = []

    if insider_sell_pct is not None and insider_sell_pct > 0.50:
        dynamic.append(RiskFlag(
            id="D01",
            name=f"Insider Sell % Exceeds Threshold ({insider_sell_pct*100:.0f}%)",
            severity=Severity.CRITICAL,
            description=f"Insider selling exceeds 50% of offering ({insider_sell_pct*100:.0f}%).",
            detail=f"Detected: {insider_sell_pct*100:.0f}% > 50% threshold",
            source="Dynamic Check",
        ))

    if h1_revenue_growth_yoy is not None and h1_revenue_growth_yoy < 0.15:
        dynamic.append(RiskFlag(
            id="D02",
            name=f"Revenue Growth Below 15% ({h1_revenue_growth_yoy*100:.0f}% YoY)",
            severity=Severity.WARNING,
            description="Growth below 15% signals maturing business at elevated IPO multiple.",
            detail=f"Detected: {h1_revenue_growth_yoy*100:.0f}% YoY",
            source="Dynamic Check",
        ))

    if float_pct is not None and float_pct < 0.15:
        dynamic.append(RiskFlag(
            id="D03",
            name=f"Public Float Below 15% ({float_pct*100:.0f}%)",
            severity=Severity.WARNING,
            description="Low float increases price volatility and reduces institutional eligibility.",
            detail=f"Detected: {float_pct*100:.0f}% < 15% standard",
            source="Dynamic Check",
        ))

    return dynamic


if __name__ == "__main__":
    flags = get_all_flags()
    score = compute_risk_score()

    print(f"\n=== GCash IPO Risk Assessment ===")
    print(f"Overall Risk Score: {score['score']}/100 — {score['label']}")
    print(f"Breakdown: {score['breakdown']}\n")

    for f in flags:
        print(f"[{f.severity.value}] {f.id} — {f.name}")
        print(f"  → {f.description[:120]}...")
        print()
