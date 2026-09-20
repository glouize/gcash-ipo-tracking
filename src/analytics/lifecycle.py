"""
src/analytics/lifecycle.py
───────────────────────────
Tracks the full GCash IPO lifecycle from SEC approval through
post-lockup analyst coverage. Provides phase detection and
critical date calculations.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional


@dataclass
class LifecycleEvent:
    name:        str
    date:        date
    phase:       str
    description: str
    is_past:     bool = False
    is_today:    bool = False
    is_upcoming: bool = False
    days_away:   int  = 0


# ── GCash IPO Key Dates ───────────────────────────────────────────────────────
GCASH_EVENTS_RAW = [
    {
        "name": "SEC Pre-Effective Letter",
        "date": date(2026, 9, 5),
        "phase": "Pre-IPO",
        "description": "SEC Philippines issued pre-effective letter — regulatory green light.",
    },
    {
        "name": "PSE Listing Approval",
        "date": date(2026, 9, 17),
        "phase": "Pre-IPO",
        "description": "Philippine Stock Exchange approved Mynt's listing application.",
    },
    {
        "name": "Roadshow / Book-Building Begins",
        "date": date(2026, 9, 20),
        "phase": "Roadshow",
        "description": "Institutional roadshow and book-building process is active.",
    },
    {
        "name": "Offer Period Opens",
        "date": date(2026, 10, 6),
        "phase": "Offer",
        "description": "Public subscription period opens. Retail investors can apply through brokers or GStocks PH.",
    },
    {
        "name": "Offer Period Closes",
        "date": date(2026, 10, 12),
        "phase": "Offer",
        "description": "Last day to subscribe. Final offer price expected to be announced.",
    },
    {
        "name": "Allotment & Refund Period",
        "date": date(2026, 10, 13),
        "phase": "Allotment",
        "description": "Share allotment processed; oversubscription refunds issued.",
    },
    {
        "name": "🚀 LISTING DAY (D+0)",
        "date": date(2026, 10, 20),
        "phase": "Listing",
        "description": "GCash begins trading on PSE Main Board under ticker GCASH.",
    },
    {
        "name": "Greenshoe Option Expiry (D+30)",
        "date": date(2026, 11, 19),
        "phase": "Post-Listing",
        "description": "Underwriter overallotment/greenshoe option expires. Price stabilization period ends.",
    },
    {
        "name": "First Quarterly Earnings (est. D+90)",
        "date": date(2027, 1, 18),
        "phase": "Post-Listing",
        "description": "First earnings release as a public company. Expected high volatility event.",
    },
    {
        "name": "⚠️ LOCKUP EXPIRY (D+180)",
        "date": date(2027, 4, 20),
        "phase": "Lockup",
        "description": (
            "Major shareholders (Globe Telecom, Ant Group, Ayala, MUFG) can sell. "
            "~88% of fully-diluted shares unlock. Significant supply shock risk."
        ),
    },
    {
        "name": "Analyst Coverage Initiations (est. D+205)",
        "date": date(2027, 5, 15),
        "phase": "Coverage",
        "description": (
            "Lead underwriter analysts typically initiate coverage ~25 days "
            "after lockup expiry. Buy ratings often accompany initiations."
        ),
    },
]


def get_lifecycle_events(today: Optional[date] = None) -> list[LifecycleEvent]:
    """
    Return all GCash IPO lifecycle events with dynamic status flags
    relative to today's date.
    """
    if today is None:
        today = date.today()

    events = []
    for raw in GCASH_EVENTS_RAW:
        d      = raw["date"]
        delta  = (d - today).days
        events.append(LifecycleEvent(
            name        = raw["name"],
            date        = d,
            phase       = raw["phase"],
            description = raw["description"],
            is_past     = d < today,
            is_today    = d == today,
            is_upcoming = d > today,
            days_away   = delta,
        ))
    return events


def get_current_phase(today: Optional[date] = None) -> str:
    """Return the name of the current IPO phase."""
    if today is None:
        today = date.today()

    phases = [
        (date(2026, 9,  5),  "Pre-IPO (Regulatory Approval)"),
        (date(2026, 9, 20),  "Roadshow & Book-Building"),
        (date(2026, 10,  6), "Public Offer Period"),
        (date(2026, 10, 13), "Allotment & Refund"),
        (date(2026, 10, 20), "Listed — Stabilization Window"),
        (date(2026, 11, 19), "Post-Greenshoe"),
        (date(2027,  1, 18), "First Earnings Approach"),
        (date(2027,  4, 20), "Approaching Lockup Expiry"),
        (date(2027,  4, 21), "Post-Lockup (True Price Discovery)"),
    ]

    current = "Pre-IPO"
    for phase_date, phase_name in phases:
        if today >= phase_date:
            current = phase_name
    return current


def days_to_listing(today: Optional[date] = None) -> int:
    """Days remaining until GCash lists on PSE (Oct 20, 2026)."""
    if today is None:
        today = date.today()
    return (date(2026, 10, 20) - today).days


def days_to_lockup_expiry(today: Optional[date] = None) -> int:
    """Days remaining until lockup expiry (Apr 20, 2027)."""
    if today is None:
        today = date.today()
    return (date(2027, 4, 20) - today).days


def compute_lockup_overhang(
    locked_shares_bn: float  = 58.87,   # Total - public float (66.9 * 0.88)
    public_float_bn: float   = 8.03,
) -> float:
    """
    Lockup Overhang Ratio = Locked Shares / Public Float.
    >3× is considered high risk of post-lockup sell-off.
    """
    return locked_shares_bn / public_float_bn


if __name__ == "__main__":
    today = date.today()
    events = get_lifecycle_events(today)

    print(f"\n=== GCash IPO Lifecycle (as of {today}) ===")
    print(f"Current Phase: {get_current_phase(today)}")
    print(f"Days to Listing: {days_to_listing(today)}")
    print(f"Days to Lockup Expiry: {days_to_lockup_expiry(today)}")
    print(f"Lockup Overhang Ratio: {compute_lockup_overhang():.1f}×\n")

    for e in events:
        status = "✅" if e.is_past else ("📍" if e.is_today else "⏳")
        days_str = f"(in {e.days_away}d)" if e.days_away > 0 else (
                   "(TODAY)" if e.days_away == 0 else f"({abs(e.days_away)}d ago)")
        print(f"{status} {e.date}  {days_str:<15}  [{e.phase}]  {e.name}")
