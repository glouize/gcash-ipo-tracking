# GCash IPO Tracking

A comprehensive data analytics and predictive tracking pipeline for the **GCash (Mynt Inc.) Initial Public Offering (IPO)** on the Philippine Stock Exchange (PSE).

**PSE Ticker:** `GCASH` · **Listing Date:** October 20, 2026 · **Target Raise:** ₱92.32B

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment (Optional)
```bash
copy .env.example .env
# Optional credentials:
#   REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET  ← free at reddit.com/prefs/apps
#   DISCORD_WEBHOOK_URL                      ← Discord webhook for alerts
```

### 3. Launch the Dashboard
```bash
streamlit run src/dashboard/app.py
```
Open **http://localhost:8501** in your browser.

---

## 📊 Dashboard Modules & Tabs

| Tab | Features |
|---|---|
| 📋 **Overview** | Revenue history (2023–2025), shareholder cap table, key IPO terms, 10 risk flags |
| 💰 **Valuation** | 5-method triangulation (P/E, EV/Rev, GP multiple, DCF, PSE precedents) + live peer comps |
| 🤖 **ML Prediction** | XGBoost Day-1 pop probability gauge, expected return, sensitivity analysis |
| 📡 **Sentiment** | Google Trends search interest, Reddit (r/phinvest) + news RSS VADER sentiment scores |
| 🗓 **Lifecycle Monitor** | Event countdown (Oct 20 listing, Apr 20 lockup expiry), lockup overhang gauge |
| 💾 **Staging & CSV Export** | SQLite append-only staging layer, incremental ETL pipeline (CDC/MD5), CSV export |

---

## 🏗️ Architecture

```
gcash-ipo-tracking/
├── data/
│   ├── gcash_staging.db       # SQLite staging database (WAL mode)
│   ├── exports/               # Generated CSV exports
│   └── training/              # ML training datasets
├── models/
│   ├── ipo_classifier.pkl     # Trained XGBoost model
│   └── scaler.pkl             # Feature scaler
├── src/
│   ├── ingestion/
│   │   ├── pse_edge_scraper.py   # PSE EDGE disclosures scraper & static prospectus data
│   │   ├── market_data.py        # Peer multiples (yfinance) & macro indicators
│   │   ├── fx_rates.py           # PHP/USD rate (BSP Open Data API + yfinance fallback)
│   │   └── sentiment.py          # Reddit (PRAW), RSS news feeds & Google Trends
│   ├── analytics/
│   │   ├── valuation.py          # 5-method fair value triangulation
│   │   ├── classifier.py         # XGBoost classifier + regressor for Day-1 return
│   │   ├── lifecycle.py          # Timeline tracker & lockup overhang calculator
│   │   └── risk_flags.py         # Automated risk flag detection engine
│   ├── storage/
│   │   └── database.py           # SQLite staging, incremental CDC engine & CSV exporter
│   ├── monitoring/
│   │   └── alerts.py             # PSE EDGE watcher scheduler + Discord webhooks
│   └── dashboard/
│       └── app.py                # 6-tab Streamlit dashboard
├── requirements.txt
├── .env.example
└── README.md
```

---

## ⚡ Full Extract & Incremental Load (CDC)

The data pipeline utilizes a **Full Source Extraction + Incremental Staging Loading** pattern:
- **Full Source Shot:** Pulls complete payload from live market feeds, valuation models, and sentiment sources.
- **Change Data Capture (CDC):** Generates deterministic MD5 record fingerprints. Only new or modified records are committed to SQLite staging, preventing duplicate bloat.
- **Audit Logging:** Every ETL execution is recorded in `etl_load_audit` and tracked in `etl_watermarks`.

To trigger the pipeline programmatically:
```python
from src.storage.database import run_full_pipeline_incremental_load

results = run_full_pipeline_incremental_load()
print(results)
```

---

## 🔔 Background PSE EDGE Disclosure Watcher

Run the background watcher to poll PSE EDGE every 4 hours and send Discord notifications:
```bash
python src/monitoring/alerts.py
```

---

*Disclaimer: This project is for educational, analytical, and research purposes only. It does not constitute financial or investment advice.*
