"""
src/storage/database.py  [GCASH]
──────────────────────────────────
SQLite staging layer for the GCash IPO Tracker.
Implements:
  1. Full Source Extraction & Incremental Staging Loading (CDC / Delta Detection)
  2. Deterministic record-hash fingerprinting (MD5) to prevent duplicate bloat
  3. Change tracking audit log (etl_load_audit) & watermarking (etl_watermarks)
  4. Analytical views for trends over time
  5. Bulk CSV export pipeline
"""

import sqlite3
import hashlib
import logging
from datetime import datetime, date
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent.parent / "data" / "gcash_staging.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
EXPORT_DIR = Path(__file__).parent.parent.parent / "data" / "exports"

# ── Schema ────────────────────────────────────────────────────────────────────
SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- Staging table: Valuation Models
CREATE TABLE IF NOT EXISTS stg_valuation_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at     TEXT    NOT NULL,
    run_date        TEXT    NOT NULL,
    method          TEXT    NOT NULL,
    low_php         REAL,
    mid_php         REAL,
    high_php        REAL,
    notes           TEXT,
    peer_ev_revenue REAL,
    peer_pe         REAL,
    record_hash     TEXT
);

-- Staging table: Peer Comps
CREATE TABLE IF NOT EXISTS stg_peer_comps (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at     TEXT    NOT NULL,
    run_date        TEXT    NOT NULL,
    ticker          TEXT    NOT NULL,
    company_name    TEXT,
    market_cap_bn   REAL,
    ev_revenue      REAL,
    ps_ratio        REAL,
    pe_ratio        REAL,
    gross_margin    REAL,
    div_yield       REAL,
    record_hash     TEXT
);

-- Staging table: Macro Indicators
CREATE TABLE IF NOT EXISTS stg_macro_snapshot (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at     TEXT    NOT NULL,
    run_date        TEXT    NOT NULL,
    vix             REAL,
    psex_30d_return REAL,
    php_usd_rate    REAL,
    record_hash     TEXT
);

-- Staging table: Daily Sentiment
CREATE TABLE IF NOT EXISTS stg_sentiment_daily (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at     TEXT    NOT NULL,
    run_date        TEXT    NOT NULL,
    sentiment_date  TEXT    NOT NULL,
    mention_count   INTEGER,
    avg_compound    REAL,
    dominant_sentiment TEXT,
    record_hash     TEXT
);

-- Staging table: Model Predictions
CREATE TABLE IF NOT EXISTS stg_predictions (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at           TEXT    NOT NULL,
    run_date              TEXT    NOT NULL,
    psex_30d_return_input REAL,
    vix_input             REAL,
    price_revision_pct    REAL,
    pop_probability       REAL,
    expected_day1_return  REAL,
    signal                TEXT,
    confidence            TEXT,
    record_hash           TEXT
);

-- Staging table: PSE Disclosures
CREATE TABLE IF NOT EXISTS stg_pse_disclosures (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at     TEXT    NOT NULL,
    disclosure_date TEXT,
    disclosure_type TEXT,
    title           TEXT    NOT NULL,
    url             TEXT,
    record_hash     TEXT,
    UNIQUE(title, disclosure_date)
);

-- ETL Pipeline Audit Log
CREATE TABLE IF NOT EXISTS etl_load_audit (
    load_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    executed_at      TEXT    NOT NULL,
    entity_name      TEXT    NOT NULL,
    load_type        TEXT    NOT NULL, -- 'FULL_EXTRACT_INCREMENTAL_LOAD' or 'FORCE_FULL'
    records_read     INTEGER NOT NULL,
    records_inserted INTEGER NOT NULL,
    records_skipped  INTEGER NOT NULL,
    status           TEXT    NOT NULL, -- 'SUCCESS', 'WARNING', 'FAILED'
    details          TEXT
);

-- ETL Watermarks Table
CREATE TABLE IF NOT EXISTS etl_watermarks (
    entity_name       TEXT PRIMARY KEY,
    last_loaded_at    TEXT NOT NULL,
    last_record_count INTEGER NOT NULL,
    last_status       TEXT NOT NULL
);

-- Analytical Views
CREATE VIEW IF NOT EXISTS v_latest_valuation AS
    SELECT * FROM stg_valuation_history
    WHERE run_date = (SELECT MAX(run_date) FROM stg_valuation_history);

CREATE VIEW IF NOT EXISTS v_valuation_trend AS
    SELECT run_date, method, mid_php, captured_at
    FROM stg_valuation_history
    WHERE method NOT LIKE '%CONSENSUS%'
    ORDER BY run_date, method;

CREATE VIEW IF NOT EXISTS v_macro_trend AS
    SELECT run_date, vix, psex_30d_return, php_usd_rate, captured_at
    FROM stg_macro_snapshot
    ORDER BY run_date;

CREATE VIEW IF NOT EXISTS v_sentiment_trend AS
    SELECT sentiment_date,
           AVG(avg_compound)  AS avg_compound,
           SUM(mention_count) AS total_mentions
    FROM stg_sentiment_daily
    GROUP BY sentiment_date
    ORDER BY sentiment_date;

CREATE VIEW IF NOT EXISTS v_prediction_trend AS
    SELECT run_date, pop_probability, expected_day1_return, signal, captured_at
    FROM stg_predictions
    ORDER BY run_date;
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create all staging tables, audit logs, and views, and migrate schema if needed."""
    with get_connection() as conn:
        conn.executescript(SCHEMA_SQL)
        # Migrate existing tables to ensure record_hash column exists
        for tbl in [
            "stg_valuation_history", "stg_peer_comps", "stg_macro_snapshot",
            "stg_sentiment_daily", "stg_predictions", "stg_pse_disclosures"
        ]:
            try:
                conn.execute(f"ALTER TABLE {tbl} ADD COLUMN record_hash TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
    logger.info("GCash staging DB initialized at %s", DB_PATH)


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"

def _today() -> str:
    return date.today().isoformat()

def _hash(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


# ── Audit & Watermark Helpers ────────────────────────────────────────────────
def log_audit(entity_name: str, load_type: str, read_count: int,
              inserted_count: int, skipped_count: int,
              status: str = "SUCCESS", details: str = "") -> None:
    sql_audit = """
    INSERT INTO etl_load_audit
    (executed_at, entity_name, load_type, records_read, records_inserted, records_skipped, status, details)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    sql_watermark = """
    INSERT INTO etl_watermarks (entity_name, last_loaded_at, last_record_count, last_status)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(entity_name) DO UPDATE SET
        last_loaded_at=excluded.last_loaded_at,
        last_record_count=excluded.last_record_count,
        last_status=excluded.last_status
    """
    now_ts = _now()
    with get_connection() as conn:
        conn.execute(sql_audit, (
            now_ts, entity_name, load_type, read_count,
            inserted_count, skipped_count, status, details
        ))
        conn.execute(sql_watermark, (entity_name, now_ts, inserted_count, status))


# ── Incremental Loaders ───────────────────────────────────────────────────────

def incremental_load_valuation(val_df: pd.DataFrame,
                               peer_ev_revenue: float = 0.0,
                               peer_pe: float = 0.0,
                               force_full: bool = False) -> dict:
    """
    Full Extraction -> Incremental Staging Load for Valuation.
    Deduplicates against existing staging records for today using MD5 hash.
    """
    if val_df.empty:
        return {"entity": "valuation", "read": 0, "inserted": 0, "skipped": 0}

    read_count = len(val_df)
    inserted = 0
    skipped = 0
    today_str = _today()
    now_ts = _now()
    rows_to_insert = []

    with get_connection() as conn:
        existing_hashes = {
            r[0] for r in conn.execute(
                "SELECT record_hash FROM stg_valuation_history WHERE run_date = ? AND record_hash IS NOT NULL",
                (today_str,)
            ).fetchall()
        }

        for _, r in val_df.iterrows():
            method = str(r.get("Method", ""))
            low = r.get("Low (₱)")
            mid = r.get("Mid (₱)")
            high = r.get("High (₱)")
            notes = str(r.get("Notes", ""))
            row_fingerprint = f"{method}|{low}|{mid}|{high}|{round(peer_ev_revenue, 2)}|{round(peer_pe, 2)}"
            rec_hash = _hash(row_fingerprint)

            if not force_full and rec_hash in existing_hashes:
                skipped += 1
                continue

            rows_to_insert.append((
                now_ts, today_str, method, low, mid, high,
                notes, peer_ev_revenue, peer_pe, rec_hash
            ))
            existing_hashes.add(rec_hash)
            inserted += 1

        if rows_to_insert:
            conn.executemany(
                """INSERT INTO stg_valuation_history
                   (captured_at, run_date, method, low_php, mid_php, high_php,
                    notes, peer_ev_revenue, peer_pe, record_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows_to_insert
            )

    load_type = "FORCE_FULL" if force_full else "FULL_EXTRACT_INCREMENTAL_LOAD"
    log_audit("valuation", load_type, read_count, inserted, skipped, "SUCCESS",
              f"Processed {read_count} source records. {inserted} new, {skipped} unchanged.")
    return {"entity": "valuation", "read": read_count, "inserted": inserted, "skipped": skipped}


def incremental_load_peer_comps(peers_df: pd.DataFrame, force_full: bool = False) -> dict:
    """
    Full Extraction -> Incremental Staging Load for Peer Comps.
    Only inserts peers whose multiples changed or haven't been stored today.
    """
    if peers_df.empty:
        return {"entity": "peer_comps", "read": 0, "inserted": 0, "skipped": 0}

    read_count = len(peers_df)
    inserted = 0
    skipped = 0
    today_str = _today()
    now_ts = _now()
    rows_to_insert = []

    with get_connection() as conn:
        existing_hashes = {
            r[0] for r in conn.execute(
                "SELECT record_hash FROM stg_peer_comps WHERE run_date = ? AND record_hash IS NOT NULL",
                (today_str,)
            ).fetchall()
        }

        for _, r in peers_df.iterrows():
            ticker = str(r.get("ticker", ""))
            name = str(r.get("name", ""))
            mcap = r.get("market_cap_bn")
            ev_rev = r.get("ev_revenue")
            ps = r.get("ps_ratio")
            pe = r.get("pe_ratio")
            gm = r.get("gross_margin")
            div = r.get("div_yield")
            row_fingerprint = f"{ticker}|{mcap}|{ev_rev}|{ps}|{pe}|{gm}|{div}"
            rec_hash = _hash(row_fingerprint)

            if not force_full and rec_hash in existing_hashes:
                skipped += 1
                continue

            rows_to_insert.append((
                now_ts, today_str, ticker, name, mcap,
                ev_rev, ps, pe, gm, div, rec_hash
            ))
            existing_hashes.add(rec_hash)
            inserted += 1

        if rows_to_insert:
            conn.executemany(
                """INSERT INTO stg_peer_comps
                   (captured_at, run_date, ticker, company_name, market_cap_bn,
                    ev_revenue, ps_ratio, pe_ratio, gross_margin, div_yield, record_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows_to_insert
            )

    load_type = "FORCE_FULL" if force_full else "FULL_EXTRACT_INCREMENTAL_LOAD"
    log_audit("peer_comps", load_type, read_count, inserted, skipped, "SUCCESS",
              f"Evaluated {read_count} peers. {inserted} new, {skipped} unchanged.")
    return {"entity": "peer_comps", "read": read_count, "inserted": inserted, "skipped": skipped}


def incremental_load_macro(vix: float, psex_30d: float, php_usd: float, force_full: bool = False) -> dict:
    """
    Full Extraction -> Incremental Staging Load for Macro signals.
    """
    read_count = 1
    today_str = _today()
    now_ts = _now()
    row_fingerprint = f"{round(vix, 2)}|{round(psex_30d, 4)}|{round(php_usd, 2)}"
    rec_hash = _hash(row_fingerprint)

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM stg_macro_snapshot WHERE run_date = ? AND record_hash = ?",
            (today_str, rec_hash)
        ).fetchone()

        if not force_full and existing:
            skipped = 1
            inserted = 0
        else:
            conn.execute(
                """INSERT INTO stg_macro_snapshot
                   (captured_at, run_date, vix, psex_30d_return, php_usd_rate, record_hash)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (now_ts, today_str, vix, psex_30d, php_usd, rec_hash)
            )
            inserted = 1
            skipped = 0

    load_type = "FORCE_FULL" if force_full else "FULL_EXTRACT_INCREMENTAL_LOAD"
    log_audit("macro_snapshot", load_type, read_count, inserted, skipped, "SUCCESS")
    return {"entity": "macro_snapshot", "read": read_count, "inserted": inserted, "skipped": skipped}


def incremental_load_sentiment(sentiment_df: pd.DataFrame, force_full: bool = False) -> dict:
    """
    Full Extraction -> Incremental Staging Load for Sentiment.
    Only inserts/updates observations with new mention counts or scores.
    """
    if sentiment_df.empty:
        return {"entity": "sentiment_daily", "read": 0, "inserted": 0, "skipped": 0}

    read_count = len(sentiment_df)
    inserted = 0
    skipped = 0
    today_str = _today()
    now_ts = _now()
    rows_to_insert = []

    with get_connection() as conn:
        existing_hashes = {
            r[0] for r in conn.execute(
                "SELECT record_hash FROM stg_sentiment_daily WHERE record_hash IS NOT NULL"
            ).fetchall()
        }

        for _, r in sentiment_df.iterrows():
            s_date = str(r.get("date", ""))
            count = int(r.get("mention_count", 0))
            compound = round(float(r.get("avg_compound", 0.0)), 4)
            dominant = str(r.get("dominant_sentiment", "Neutral"))
            row_fingerprint = f"{s_date}|{count}|{compound}|{dominant}"
            rec_hash = _hash(row_fingerprint)

            if not force_full and rec_hash in existing_hashes:
                skipped += 1
                continue

            rows_to_insert.append((
                now_ts, today_str, s_date, count, compound, dominant, rec_hash
            ))
            existing_hashes.add(rec_hash)
            inserted += 1

        if rows_to_insert:
            conn.executemany(
                """INSERT INTO stg_sentiment_daily
                   (captured_at, run_date, sentiment_date, mention_count,
                    avg_compound, dominant_sentiment, record_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                rows_to_insert
            )

    load_type = "FORCE_FULL" if force_full else "FULL_EXTRACT_INCREMENTAL_LOAD"
    log_audit("sentiment_daily", load_type, read_count, inserted, skipped, "SUCCESS")
    return {"entity": "sentiment_daily", "read": read_count, "inserted": inserted, "skipped": skipped}


def incremental_load_predictions(pred: dict, psex_input: float = 0.0,
                                 vix_input: float = 18.0, price_rev: float = 0.0,
                                 force_full: bool = False) -> dict:
    read_count = 1
    today_str = _today()
    now_ts = _now()
    prob = pred.get("pop_probability")
    exp_ret = pred.get("expected_day1_return")
    sig = pred.get("signal")
    conf = pred.get("confidence")
    row_fingerprint = f"{psex_input}|{vix_input}|{price_rev}|{prob}|{exp_ret}|{sig}|{conf}"
    rec_hash = _hash(row_fingerprint)

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM stg_predictions WHERE run_date = ? AND record_hash = ?",
            (today_str, rec_hash)
        ).fetchone()

        if not force_full and existing:
            skipped = 1
            inserted = 0
        else:
            conn.execute(
                """INSERT INTO stg_predictions
                   (captured_at, run_date, psex_30d_return_input, vix_input,
                    price_revision_pct, pop_probability, expected_day1_return,
                    signal, confidence, record_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (now_ts, today_str, psex_input, vix_input, price_rev, prob, exp_ret, sig, conf, rec_hash)
            )
            inserted = 1
            skipped = 0

    load_type = "FORCE_FULL" if force_full else "FULL_EXTRACT_INCREMENTAL_LOAD"
    log_audit("predictions", load_type, read_count, inserted, skipped, "SUCCESS")
    return {"entity": "predictions", "read": read_count, "inserted": inserted, "skipped": skipped}


def incremental_load_disclosures(disclosures: list[dict], force_full: bool = False) -> dict:
    if not disclosures:
        return {"entity": "pse_disclosures", "read": 0, "inserted": 0, "skipped": 0}

    read_count = len(disclosures)
    inserted = 0
    skipped = 0
    now_ts = _now()
    rows_to_insert = []

    with get_connection() as conn:
        existing_hashes = {
            r[0] for r in conn.execute(
                "SELECT record_hash FROM stg_pse_disclosures WHERE record_hash IS NOT NULL"
            ).fetchall()
        }

        for d in disclosures:
            ddate = str(d.get("date", ""))
            dtype = str(d.get("type", ""))
            title = str(d.get("title", ""))
            url = str(d.get("url", ""))
            rec_hash = _hash(f"{title}|{ddate}|{url}")

            if not force_full and rec_hash in existing_hashes:
                skipped += 1
                continue

            rows_to_insert.append((now_ts, ddate, dtype, title, url, rec_hash))
            existing_hashes.add(rec_hash)
            inserted += 1

        if rows_to_insert:
            conn.executemany(
                """INSERT OR IGNORE INTO stg_pse_disclosures
                   (captured_at, disclosure_date, disclosure_type, title, url, record_hash)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                rows_to_insert
            )

    load_type = "FORCE_FULL" if force_full else "FULL_EXTRACT_INCREMENTAL_LOAD"
    log_audit("pse_disclosures", load_type, read_count, inserted, skipped, "SUCCESS")
    return {"entity": "pse_disclosures", "read": read_count, "inserted": inserted, "skipped": skipped}


# ── Full Extract & Incremental Load Orchestrator ─────────────────────────────
def run_full_pipeline_incremental_load(force_full: bool = False) -> list[dict]:
    """
    Executes a Full Source Extraction across all endpoints and loads deltas into staging.
    """
    from src.analytics.valuation import run_all_methods
    from src.ingestion.market_data import fetch_peer_info, compute_peer_medians, get_vix_latest, get_psex_30d_return
    from src.ingestion.fx_rates import get_php_usd_rate
    from src.ingestion.sentiment import build_daily_sentiment
    from src.ingestion.pse_edge_scraper import fetch_pse_disclosures
    from src.analytics.classifier import predict_gcash

    results = []

    # 1. Peers & Valuation (Full Extraction)
    peers = fetch_peer_info()
    medians = compute_peer_medians(peers) if not peers.empty else {}
    ev_rev = float(medians.get("median_ev_revenue", 5.5) or 5.5)
    pe = float(medians.get("median_pe_ratio", 28.0) or 28.0)
    val_df = run_all_methods(peer_ev_revenue=ev_rev, peer_pe=pe)

    results.append(incremental_load_peer_comps(peers, force_full=force_full))
    results.append(incremental_load_valuation(val_df, peer_ev_revenue=ev_rev, peer_pe=pe, force_full=force_full))

    # 2. Macro Snapshot (Full Extraction)
    vix = get_vix_latest() or 18.0
    psex = get_psex_30d_return() or 0.0
    rate = get_php_usd_rate()
    results.append(incremental_load_macro(vix, psex, rate, force_full=force_full))

    # 3. Model Prediction
    pred = predict_gcash(psex_30d_return=psex, vix=vix)
    results.append(incremental_load_predictions(pred, psex_input=psex, vix_input=vix, force_full=force_full))

    # 4. Daily Sentiment (Full Extraction)
    daily_sent = build_daily_sentiment(days_back=14)
    if not daily_sent.empty:
        results.append(incremental_load_sentiment(daily_sent, force_full=force_full))

    # 5. PSE Disclosures (Full Extraction)
    try:
        disc = fetch_pse_disclosures()
        if disc:
            results.append(incremental_load_disclosures(disc, force_full=force_full))
    except Exception as e:
        logger.warning("Disclosure incremental extract skipped: %s", e)

    return results


# ── Backward Compatible API Wrappers ─────────────────────────────────────────
def write_valuation(val_df: pd.DataFrame, peer_ev_revenue: float = 0.0, peer_pe: float = 0.0) -> int:
    res = incremental_load_valuation(val_df, peer_ev_revenue, peer_pe)
    return res["inserted"]

def write_peer_comps(peers_df: pd.DataFrame) -> int:
    res = incremental_load_peer_comps(peers_df)
    return res["inserted"]

def write_macro(vix: float, psex_30d: float, php_usd: float) -> None:
    incremental_load_macro(vix, psex_30d, php_usd)

def write_sentiment(sentiment_df: pd.DataFrame) -> int:
    res = incremental_load_sentiment(sentiment_df)
    return res["inserted"]

def write_prediction(pred: dict, psex_input: float = 0.0, vix_input: float = 18.0, price_rev: float = 0.0) -> None:
    incremental_load_predictions(pred, psex_input, vix_input, price_rev)

def write_disclosures(disclosures: list[dict]) -> int:
    res = incremental_load_disclosures(disclosures)
    return res["inserted"]


# ── Readers ───────────────────────────────────────────────────────────────────
def read_table(table_or_view: str) -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query(f"SELECT * FROM {table_or_view}", conn)


def get_db_summary() -> dict:
    tables = [
        "stg_valuation_history",
        "stg_peer_comps",
        "stg_macro_snapshot",
        "stg_sentiment_daily",
        "stg_predictions",
        "stg_pse_disclosures",
        "etl_load_audit",
    ]
    summary = {}
    with get_connection() as conn:
        for t in tables:
            try:
                count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                date_col = "executed_at" if t == "etl_load_audit" else "run_date"
                first = conn.execute(f"SELECT MIN({date_col}) FROM {t}").fetchone()[0]
                last  = conn.execute(f"SELECT MAX({date_col}) FROM {t}").fetchone()[0]
                summary[t] = {"rows": count, "first_date": first, "last_date": last}
            except Exception:
                summary[t] = {"rows": 0, "first_date": None, "last_date": None}
    return summary


def get_audit_log(limit: int = 50) -> pd.DataFrame:
    sql = f"SELECT * FROM etl_load_audit ORDER BY load_id DESC LIMIT {limit}"
    with get_connection() as conn:
        return pd.read_sql_query(sql, conn)


def get_watermarks() -> pd.DataFrame:
    sql = "SELECT * FROM etl_watermarks ORDER BY entity_name"
    with get_connection() as conn:
        return pd.read_sql_query(sql, conn)


# ── CSV Export ────────────────────────────────────────────────────────────────
def export_all_to_csv() -> dict[str, Path]:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    exports = {}
    tables_and_views = [
        "stg_valuation_history",
        "stg_peer_comps",
        "stg_macro_snapshot",
        "stg_sentiment_daily",
        "stg_predictions",
        "stg_pse_disclosures",
        "etl_load_audit",
        "etl_watermarks",
        "v_valuation_trend",
        "v_macro_trend",
        "v_sentiment_trend",
        "v_prediction_trend",
    ]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    for name in tables_and_views:
        try:
            df   = read_table(name)
            path = EXPORT_DIR / f"gcash_{name}_{ts}.csv"
            df.to_csv(path, index=False)
            exports[name] = path
            logger.info("Exported %s → %s (%d rows)", name, path.name, len(df))
        except Exception as e:
            logger.warning("Export failed for %s: %s", name, e)
    return exports


init_db()
