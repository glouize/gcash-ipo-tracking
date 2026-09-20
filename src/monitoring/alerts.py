"""
src/monitoring/alerts.py + pse_edge_watcher.py
────────────────────────────────────────────────
PSE EDGE disclosure watcher and Discord/webhook alert dispatcher.
Polls PSE EDGE every 4 hours for new Mynt/GCASH filings.
"""

import hashlib
import json
import logging
import os
import time
from datetime import date, datetime
from pathlib import Path

import requests
from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

WEBHOOK_URL  = os.getenv("DISCORD_WEBHOOK_URL", "")
STATE_FILE   = Path(__file__).parent.parent.parent / "data" / "processed" / "watcher_state.json"
PSE_EDGE_RSS = "https://edge.pse.com.ph/rss"   # PSE EDGE RSS (check availability)

# ── Key GCash Alert Dates ─────────────────────────────────────────────────────
ALERT_DATES = {
    date(2026, 10,  6): "📢 GCash Offer Period OPENS today! You can now subscribe.",
    date(2026, 10, 12): "⏰ GCash Offer Period CLOSES today! Last chance to subscribe.",
    date(2026, 10, 19): "🚀 GCash lists on PSE TOMORROW (Oct 20)! Get ready.",
    date(2026, 10, 20): "🎉 GCash (GCASH) is NOW LIVE on the PSE! Listing Day!",
    date(2026, 11, 12): "⚠️ Greenshoe expiry in 7 days (Nov 19). Stabilization window closing.",
    date(2026, 11, 19): "📊 GCash greenshoe/overallotment option expires today.",
    date(2027,  4, 13): "🔓 LOCKUP EXPIRY in 7 days (Apr 20)! Major shareholders can sell. Monitor volume.",
    date(2027,  4, 19): "🚨 GCash lockup expiry TOMORROW (Apr 20). Expect elevated volatility.",
    date(2027,  4, 20): "🔓 GCash LOCKUP EXPIRED. Globe/Ant/Ayala shares now unlockable. Watch for block trades.",
}


# ─────────────────────────────────────────────────────────────────────────────
# Discord Webhook Alerts
# ─────────────────────────────────────────────────────────────────────────────

def send_discord_alert(message: str, title: str = "GCash IPO Tracker", color: int = 0x00B0FF) -> bool:
    """
    Send a rich embed alert to a Discord channel via webhook.

    Args:
        message: Alert body text (markdown supported)
        title:   Embed title
        color:   Embed sidebar color (hex int)

    Returns True if sent successfully.
    """
    if not WEBHOOK_URL:
        logger.warning("No DISCORD_WEBHOOK_URL set — alert not sent: %s", message)
        return False

    payload = {
        "embeds": [{
            "title":       title,
            "description": message,
            "color":       color,
            "footer":      {"text": f"GCash IPO Tracker • {datetime.now().strftime('%Y-%m-%d %H:%M PHT')}"},
        }]
    }

    try:
        resp = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info("Discord alert sent: %s", title)
        return True
    except Exception as e:
        logger.error("Discord alert failed: %s", e)
        return False


def send_date_alert(today: date | None = None) -> None:
    """Check if today matches a pre-scheduled alert date and fire it."""
    if today is None:
        today = date.today()
    if today in ALERT_DATES:
        send_discord_alert(
            message=ALERT_DATES[today],
            title=f"📅 GCash IPO Alert — {today.strftime('%b %d, %Y')}",
            color=0xFF6B00,
        )


# ─────────────────────────────────────────────────────────────────────────────
# PSE EDGE Watcher
# ─────────────────────────────────────────────────────────────────────────────

def _load_state() -> dict:
    """Load the last-seen disclosure hashes from disk."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"seen_hashes": []}


def _save_state(state: dict) -> None:
    """Persist disclosure hashes to disk."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _hash_disclosure(title: str, date_str: str) -> str:
    return hashlib.md5(f"{title}|{date_str}".encode()).hexdigest()


def check_pse_edge_for_new_disclosures() -> list[dict]:
    """
    Poll PSE EDGE for new Mynt / GCASH disclosures.
    Returns a list of new (unseen) disclosures.
    """
    # Import here to avoid circular deps
    from src.ingestion.pse_edge_scraper import fetch_pse_disclosures

    state    = _load_state()
    seen     = set(state.get("seen_hashes", []))
    all_disc = fetch_pse_disclosures("Mynt")
    new_disc = []

    for d in all_disc:
        h = _hash_disclosure(d.get("title", ""), d.get("date", ""))
        if h not in seen:
            new_disc.append(d)
            seen.add(h)

    if new_disc:
        _save_state({"seen_hashes": list(seen), "last_checked": datetime.now().isoformat()})
        logger.info("Found %d new PSE EDGE disclosures", len(new_disc))
    else:
        logger.info("No new PSE EDGE disclosures found")

    return new_disc


def process_new_disclosures(disclosures: list[dict]) -> None:
    """Send Discord alerts for each new PSE EDGE disclosure."""
    for d in disclosures:
        title   = d.get("title", "New disclosure")
        dtype   = d.get("type", "Filing")
        ddate   = d.get("date", "")
        url     = d.get("url", "")

        # Check if it's a price amendment (critical signal)
        is_price_amendment = any(
            kw in title.lower()
            for kw in ["amended", "price range", "offer price", "revised", "amendment"]
        )

        color   = 0xFF0000 if is_price_amendment else 0x00B0FF
        urgency = "🚨 PRICE RANGE AMENDMENT DETECTED" if is_price_amendment else "📄 New Disclosure"

        message = (
            f"**{urgency}**\n\n"
            f"**Type:** {dtype}\n"
            f"**Date:** {ddate}\n"
            f"**Title:** {title}\n"
            f"**Link:** {url or 'See PSE EDGE'}"
        )

        if is_price_amendment:
            message += (
                "\n\n⚡ **Action:** Re-running valuation model with updated price range. "
                "Check dashboard for updated fair value estimates."
            )

        send_discord_alert(
            message=message,
            title="GCash IPO — PSE EDGE Update",
            color=color,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Scheduler (APScheduler)
# ─────────────────────────────────────────────────────────────────────────────

def run_watcher_job() -> None:
    """Single watcher tick: check PSE EDGE + send date alerts."""
    logger.info("[%s] Running watcher job...", datetime.now().strftime("%Y-%m-%d %H:%M"))

    # 1. Date-based alerts
    send_date_alert()

    # 2. PSE EDGE new disclosure check
    try:
        new = check_pse_edge_for_new_disclosures()
        if new:
            process_new_disclosures(new)
    except Exception as e:
        logger.error("Watcher job error: %s", e)


def start_scheduler(interval_hours: int = 4) -> None:
    """
    Start the APScheduler background scheduler.
    Runs the watcher job every `interval_hours` hours.
    """
    scheduler = BlockingScheduler(timezone="Asia/Manila")
    scheduler.add_job(
        run_watcher_job,
        trigger="interval",
        hours=interval_hours,
        next_run_time=datetime.now(),   # Run immediately on start
        id="pse_watcher",
    )

    logger.info("PSE EDGE watcher started — polling every %d hours (Manila time)", interval_hours)
    print(f"\n✅ Watcher running. Polling PSE EDGE every {interval_hours} hours.")
    print("   Press Ctrl+C to stop.\n")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Watcher stopped by user.")
        print("\nWatcher stopped.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Test: send a test Discord alert
    result = send_discord_alert(
        message=(
            "✅ **GCash IPO Tracker is active!**\n\n"
            "Monitoring PSE EDGE for new disclosures every 4 hours.\n"
            "Listing Date: **October 20, 2026**\n"
            "Offer Period: **October 6–12, 2026**"
        ),
        title="🚀 GCash IPO Tracker — Started",
        color=0x00C853,
    )
    if result:
        print("Discord test alert sent successfully!")
    else:
        print("Discord webhook not configured (set DISCORD_WEBHOOK_URL in .env)")

    # Start scheduler
    start_scheduler(interval_hours=4)
