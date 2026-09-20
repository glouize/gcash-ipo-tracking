# GCash IPO Tracking & Predictive Analytics Pipeline

[![Streamlit](https://img.shields.io/badge/Streamlit-1.42+-FF4B4B.svg?style=for-the-badge&logo=Streamlit&logoColor=white)](https://streamlit.io/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg?style=for-the-badge&logo=python&logoColor=white)](https://python.org/)
[![XGBoost](https://img.shields.io/badge/XGBoost-2.1+-EB5424.svg?style=for-the-badge&logo=xgboost&logoColor=white)](https://xgboost.readthedocs.io/)
[![SQLite](https://img.shields.io/badge/SQLite-WAL_Staging-003B57.svg?style=for-the-badge&logo=sqlite&logoColor=white)](https://sqlite.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)](LICENSE)

A high-performance quantitative research, valuation, and predictive tracking pipeline for the upcoming **GCash (Globe Fintech Innovations, Inc. / Mynt)** Initial Public Offering on the Philippine Stock Exchange (PSE).

---

## 📸 Dashboard Snapshot

![GCash IPO Tracker Dashboard](assets/dashboard_snapshot.png)

*Interactive 6-tab Streamlit dashboard running live at `http://localhost:8501`.*

---

## 📌 Executive Summary & IPO Context

GCash (operated by Mynt) is the Philippines' dominant fintech superapp with over **94 million registered users** and ubiquity across payments, lending, remittances, savings, and investments. The upcoming listing represents the **largest IPO in Philippine capital markets history**.

| Parameter | Key Detail |
|---|---|
| **Issuer** | Globe Fintech Innovations, Inc. (Mynt) |
| **PSE Ticker** | `GCASH` |
| **Target Raise** | **₱92.32 Billion** (~US$1.50 Billion) |
| **Maximum Offer Price** | **₱10.00** per share |
| **Analyst Target Range** | **₱7.50 – ₱8.50** per share |
| **Total Diluted Shares** | **66.90 Billion** shares |
| **Implied Market Cap** | **₱501B – ₱669B** (~US$8.3B – $11.1B) |
| **Public Float** | **12.0%** *(SEC exemption from standard 15% rule)* |
| **Offer Period** | **October 6 – 12, 2026** |
| **Listing Date** | **October 20, 2026** |
| **Cornerstone / Lockup** | **180 days** $\rightarrow$ **Expiry: April 20, 2027** |
| **Major Shareholders** | Globe Telecom (~45%), Ant Group (~33%), Ayala Corp (~10%), MUFG (~5%) |

---

## 🔬 Core Analytical Capabilities

### 1. 5-Method Fair Value Triangulation
Rather than relying on a single multiple, the engine computes intrinsic and relative value across 5 independent models:
1. **EV / Revenue Multiple:** Calibrated against global & regional fintech peers (Block, PayPal, Sea Ltd, Grab, Nu Holdings) adjusted for emerging-market risk discount.
2. **Gross Profit Multiple:** Growth-adjusted multiple based on Rule-of-40 SaaS/Fintech benchmarks.
3. **P/E Multiple:** Applied to NTM net income projections (2025 net income: ₱17.2B at 21.6% net margin).
4. **5-Year Discounted Cash Flow (DCF):** Scenario-based (Bear: 15% CAGR / 13% WACC; Base: 25% CAGR / 11% WACC; Bull: 35% CAGR / 10% WACC, 3.5% terminal growth).
5. **PSE Precedent IPO Multiples:** Benchmarked against historical Philippine mega-listings (*Monde Nissin, Converge ICT, Del Monte, Solar Philippines*).

### 2. Machine Learning Day-1 Pop Prediction
- **Architecture:** Dual-headed XGBoost model (Classification for Day-1 Pop $> +10\%$ + Regression for expected Day-1 return percentage).
- **Feature Space (20 Factors):**
  - Trailing 30-day PSEi market momentum & global equity sentiment
  - Real-time CBOE VIX volatility index on listing day
  - Offer pricing revision percentage vs. maximum filing price
  - Lockup overhang ratio ($\text{Locked Shares} / \text{Float}$)
  - Primary vs. secondary shares distribution
  - Institutional book subscription coverage ratio
  - Revenue growth acceleration/deceleration metrics
- **Interactive Scenario Sensitivity:** Test market shocks in real-time (e.g., Bear market: PSEi $-10\%$, VIX $30 \rightarrow$ predicted return; Bull market: PSEi $+5\%$, VIX $15 \rightarrow$ predicted return).

### 3. Automated Risk Flag Detection (10 Key Triggers)
Automated multi-factor risk scoring engine categorizing threats into **🚨 Critical**, **⚠️ Warning**, **ℹ️ Info**, and **✅ Clear**:
- **🚨 80% Secondary Shares (Capital Extraction):** ₱73.8B of the ₱92.3B raise goes directly to existing shareholders cashing out (Globe, Ant Group, Ayala), leaving only 20% for primary growth capital.
- **🚨 7.3× Lockup Overhang Ratio:** On April 20, 2027, 58.8B locked shares become eligible for sale against a float of only 8.0B shares, posing substantial post-lockup supply pressure.
- **⚠️ Public Float Below PSE 15% Standard:** 12% float granted special exemption, restricting initial market liquidity.
- **⚠️ Decelerating H1 2026 Revenue:** Revenue growth slowed from $+45\%$ YoY (2025) to $+10\%$ YoY (H1 2026), suggesting domestic market penetration saturation.
- **✅ High Profitability:** Strong cash generation (₱17.2B FY2025 net income; 21.6% net margin).

### 4. Natural Language Sentiment & News Monitoring
- **Social Sentiment:** Scrapes Philippine investing communities (`r/phinvest`, `r/PHStockMarket`, `r/philippines`) via Reddit PRAW API.
- **Financial News Feed:** Parses RSS feeds across BusinessWorld, Philippine Star, Inquirer Business, and Manila Bulletin.
- **VADER Sentiment Engine:** Generates daily compound polarity scores (-1.0 to +1.0) and volume velocity indicators.
- **Google Trends:** Monitors normalized PH search volume for "GCash IPO".

### 5. SQLite Staging Layer & Incremental CDC Engine
- **Full Shot Extraction:** Extracts complete payload from live market APIs, news, and valuation models.
- **Change Data Capture (CDC):** Generates deterministic MD5 record fingerprints across business keys (`ticker + run_date`, `sentiment_date`, `method`).
- **Delta Persistence:** Only new or modified records are written to SQLite staging (`data/gcash_staging.db` in WAL mode), preventing duplicate data bloat.
- **Audit Logging & Watermarks:** Logs every ETL execution to `etl_load_audit` and updates `etl_watermarks`.
- **Bulk CSV Exporter:** One-click automated export of all staging tables and analytical views to `data/exports/`.

---

## 🏛️ System Architecture

```
gcash-ipo-tracking/
│
├── assets/
│   └── dashboard_snapshot.png     # Full dashboard screenshot
│
├── data/
│   ├── gcash_staging.db           # SQLite WAL staging database
│   ├── exports/                   # Automated CSV export destination
│   └── training/                  # Historical PSE IPO training dataset
│
├── models/
│   ├── ipo_classifier.pkl         # Trained XGBoost classifier & regressor
│   └── scaler.pkl                 # StandardScaler feature preprocessor
│
├── src/
│   ├── ingestion/
│   │   ├── pse_edge_scraper.py    # PSE EDGE disclosure scraper & prospectus facts
│   │   ├── market_data.py         # yfinance peer multiples & macro data (VIX, PSEi)
│   │   ├── fx_rates.py            # BSP Open Data API + yfinance fallback
│   │   └── sentiment.py           # Reddit PRAW + News RSS + Google Trends
│   ├── analytics/
│   │   ├── valuation.py           # 5-method valuation triangulation engine
│   │   ├── classifier.py          # XGBoost prediction pipeline & sensitivity analysis
│   │   ├── lifecycle.py           # Timeline tracker & lockup overhang calculator
│   │   └── risk_flags.py          # Automated 10-point risk flag evaluation
│   ├── storage/
│   │   └── database.py            # SQLite staging layer, incremental CDC & CSV exporter
│   ├── monitoring/
│   │   └── alerts.py              # Automated 4-hour PSE EDGE watcher & Discord webhooks
│   └── dashboard/
│       └── app.py                 # Streamlit 6-tab dashboard UI
│
├── scripts/
│   └── capture_snapshot.py        # Headless Chrome/Edge CDP screenshot utility
│
├── requirements.txt               # Locked production dependencies
├── .env.example                   # API credentials template
├── .gitignore                     # Git exclusion rules
└── README.md                      # Project documentation
```

---

## ⚡ Quick Start

### 1. Clone & Setup Environment
```bash
git clone https://github.com/glouize/gcash-ipo-tracking.git
cd gcash-ipo-tracking

# Create and activate virtual environment (optional)
python -m venv venv
venv\Scripts\activate      # Windows
source venv/bin/activate   # Linux/macOS

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Configuration (Optional)
```bash
cp .env.example .env
```
Configure your optional free credentials:
- `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`: Free from [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)
- `DISCORD_WEBHOOK_URL`: Discord channel webhook for automated filings and countdown alerts

### 3. Launch Dashboard
```bash
streamlit run src/dashboard/app.py
```
Open **[http://localhost:8501](http://localhost:8501)** in your browser.

---

## 🖥️ Dashboard Navigation (6 Tabs)

| Tab | Icon | Key Features |
|---|:---:|---|
| **Overview** | 📋 | Executive IPO facts, cap table donut chart, 2023–2025 revenue/net income dual-axis chart, severity-filtered risk cards |
| **Valuation** | 💰 | 5-method fair value table (Low/Mid/High), price target dispersion chart, live fintech peer comparables table |
| **ML Prediction** | 🤖 | XGBoost Day-1 pop probability gauge, expected % return, feature importance chart, multi-scenario sensitivity stress-test |
| **Sentiment** | 📡 | Google Trends 90-day search velocity, Reddit + news VADER score bar chart, macro context indicators (VIX, PSEi, PHP/USD) |
| **Lifecycle Monitor** | 🗓 | Countdown to listing day and lockup expiry, timeline table, lockup period progress bar, Discord status |
| **Staging & CSV Export** | 💾 | SQLite database status card, **⚡ Run Incremental Pipeline** button, audit log, table explorer with in-browser CSV download & bulk disk export |

---

## 💾 Staging Database Schema & Views

### Staging Tables
- `stg_valuation_history`: Time-series fair value estimates across all 5 models.
- `stg_peer_comps`: Daily financial multiples of fintech peers (Block, PayPal, Sea Ltd, Grab, Nubank).
- `stg_macro_snapshot`: Daily closing VIX, trailing 30-day PSEi return, and BSP PHP/USD exchange rate.
- `stg_sentiment_daily`: Aggregated social and news polarity scores.
- `stg_predictions`: Historical record of ML predictions and input assumptions.
- `stg_pse_disclosures`: Formal company disclosures filed on PSE EDGE.
- `etl_load_audit`: Audit trail tracking pipeline runs (`records_read`, `records_inserted`, `records_skipped`, status).
- `etl_watermarks`: High-water marks for each pipeline domain.

### Pre-built Analytical Views
- `v_valuation_trend`: Fair value evolution over time.
- `v_macro_trend`: Macro volatility and FX movement preceding listing.
- `v_sentiment_trend`: Moving average sentiment leading into the offer period.
- `v_prediction_trend`: Trajectory of ML probability forecasts.
- `v_latest_valuation`: Active consensus estimate from the latest execution.

---

## 🔔 Background Automation (PSE EDGE Watcher)

Run the standalone background monitoring daemon to poll PSE EDGE every 4 hours for official prospectus updates and send Discord alerts:
```bash
python src/monitoring/alerts.py
```

---

## 📜 Disclaimer
*This repository is created solely for quantitative research, financial modeling, and software engineering demonstration purposes. Nothing contained herein constitutes investment, financial, legal, or tax advice. Market projections and machine learning estimates are probabilistic simulations based on publicly available information and synthetic historical benchmarks.*
