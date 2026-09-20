"""
src/analytics/features.py + classifier.py
───────────────────────────────────────────
Feature engineering and XGBoost-based Day-1 pop classifier for GCash IPO.
Trained on PSE + SEA historical IPO data.
"""

import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    classification_report, roc_auc_score, mean_absolute_error
)
import xgboost as xgb
import joblib

logger = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).parent.parent.parent / "models" / "ipo_classifier.pkl"
SCALER_PATH = Path(__file__).parent.parent.parent / "models" / "scaler.pkl"

# ── Feature Definitions ───────────────────────────────────────────────────────
FEATURE_COLS = [
    "revenue_growth_yoy",
    "net_margin",
    "gross_margin",
    "float_pct",
    "insider_selling_pct",
    "secondary_pct",
    "lockup_overhang_ratio",
    "days_s1_to_ipo",
    "ipo_month",
    "price_range_revision_pct",
    "underwriter_tier",
    "concurrent_ipo_count",
    "psex_30d_return",
    "vix_on_pricing_day",
    "pe_ratio",
    "ev_revenue_multiple_at_ipo",
    "mau_millions",
    "profitable_flag",
    "em_market_flag",
    "dual_class_flag",
]

TARGET_CLASS = "day1_pop_gt10pct"   # Binary: Day-1 return > 10%
TARGET_REG   = "day1_return_pct"    # Continuous: actual Day-1 return


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic Training Data (PSE + SEA IPO approximations, 2015–2025)
# ─────────────────────────────────────────────────────────────────────────────
# In production: replace with actual scraped PSE EDGE + Bloomberg IPO data.
# This synthetic dataset captures the known statistical patterns.

def generate_synthetic_ipo_data(n: int = 300, seed: int = 42) -> pd.DataFrame:
    """
    Generate a synthetic historical IPO dataset calibrated to PSE + SEA patterns.
    Used to train the classifier when real historical data is unavailable.
    """
    rng = np.random.default_rng(seed)

    df = pd.DataFrame({
        "revenue_growth_yoy":         rng.uniform(0.05, 1.20, n),
        "net_margin":                  rng.uniform(-0.30, 0.35, n),
        "gross_margin":                rng.uniform(0.20, 0.85, n),
        "float_pct":                   rng.uniform(0.10, 0.40, n),
        "insider_selling_pct":         rng.uniform(0.00, 0.90, n),
        "secondary_pct":               rng.uniform(0.00, 0.90, n),
        "lockup_overhang_ratio":       rng.uniform(0.5, 12.0, n),
        "days_s1_to_ipo":              rng.integers(30, 180, n).astype(float),
        "ipo_month":                   rng.integers(1, 13, n).astype(float),
        "price_range_revision_pct":    rng.uniform(-0.15, 0.20, n),
        "underwriter_tier":            rng.choice([1, 2, 3], n, p=[0.3, 0.4, 0.3]).astype(float),
        "concurrent_ipo_count":        rng.integers(0, 8, n).astype(float),
        "psex_30d_return":             rng.uniform(-0.15, 0.20, n),
        "vix_on_pricing_day":          rng.uniform(10, 35, n),
        "pe_ratio":                    rng.uniform(10, 60, n),
        "ev_revenue_multiple_at_ipo":  rng.uniform(1.0, 12.0, n),
        "mau_millions":                rng.uniform(0, 50, n),
        "profitable_flag":             rng.choice([0, 1], n, p=[0.55, 0.45]).astype(float),
        "em_market_flag":              rng.choice([0, 1], n, p=[0.40, 0.60]).astype(float),
        "dual_class_flag":             rng.choice([0, 1], n, p=[0.80, 0.20]).astype(float),
    })

    # Generate realistic Day-1 returns based on key features
    # Higher pop probability when: small float, high price revision, profitable, low secondary
    signal = (
        0.30 * (df["price_range_revision_pct"] / 0.20)    # Strong upward revision → pop
      - 0.20 * (df["insider_selling_pct"] - 0.30)         # High insider sell → suppress
      + 0.15 * df["profitable_flag"]                       # Profitability premium
      - 0.15 * (df["vix_on_pricing_day"] - 20) / 15       # High VIX → suppress
      + 0.10 * (df["psex_30d_return"] / 0.10)             # Strong market → boost
      - 0.10 * (df["float_pct"] - 0.15) / 0.15            # Higher float → less pop
      + rng.normal(0, 0.15, n)                             # Random noise
    )

    df[TARGET_REG]   = (signal * 0.30).clip(-0.40, 0.80)
    df[TARGET_CLASS] = (df[TARGET_REG] > 0.10).astype(int)

    return df


# ─────────────────────────────────────────────────────────────────────────────
# Model Training
# ─────────────────────────────────────────────────────────────────────────────

def train_classifier(data: pd.DataFrame | None = None) -> dict:
    """
    Train XGBoost classifier and regressor on historical IPO data.
    Saves models to disk at MODEL_PATH / SCALER_PATH.

    Returns: dict with train/test metrics.
    """
    if data is None:
        logger.info("No data provided — generating synthetic training set (n=300)")
        data = generate_synthetic_ipo_data()

    X = data[FEATURE_COLS]
    y_cls = data[TARGET_CLASS]
    y_reg = data[TARGET_REG]

    X_train, X_test, yc_train, yc_test, yr_train, yr_test = train_test_split(
        X, y_cls, y_reg, test_size=0.20, random_state=42, stratify=y_cls
    )

    # Scale features
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s  = scaler.transform(X_test)

    # ── Classifier ──────────────────────────────────────────────────────────
    clf = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        use_label_encoder=False,
        eval_metric="logloss",
        random_state=42,
    )
    clf.fit(X_train_s, yc_train)
    yc_pred = clf.predict(X_test_s)
    yc_prob = clf.predict_proba(X_test_s)[:, 1]

    # ── Regressor ───────────────────────────────────────────────────────────
    reg = xgb.XGBRegressor(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
    )
    reg.fit(X_train_s, yr_train)
    yr_pred = reg.predict(X_test_s)

    # Save models
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"classifier": clf, "regressor": reg}, MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)
    logger.info("Models saved to %s", MODEL_PATH)

    metrics = {
        "auc":              round(roc_auc_score(yc_test, yc_prob), 3),
        "classification":   classification_report(yc_test, yc_pred, output_dict=True),
        "mae_day1_return":  round(mean_absolute_error(yr_test, yr_pred), 3),
        "feature_importance": dict(zip(FEATURE_COLS, clf.feature_importances_.tolist())),
    }
    logger.info("Classifier AUC: %.3f | Day-1 Return MAE: %.3f", metrics["auc"], metrics["mae_day1_return"])
    return metrics


# ─────────────────────────────────────────────────────────────────────────────
# GCash Prediction
# ─────────────────────────────────────────────────────────────────────────────

# GCash feature vector — update psex_30d_return and vix_on_pricing_day at runtime
GCASH_FEATURES = {
    "revenue_growth_yoy":        0.10,   # H1 2026 YoY — decelerating
    "net_margin":                0.249,  # H1 2026
    "gross_margin":              0.63,   # Estimated
    "float_pct":                 0.12,   # 12% public float
    "insider_selling_pct":       0.80,   # 80% secondary offering
    "secondary_pct":             0.80,
    "lockup_overhang_ratio":     7.35,   # 58.87B locked / 8.03B float
    "days_s1_to_ipo":            45.0,   # Sept → Oct (fast)
    "ipo_month":                 10.0,   # October
    "price_range_revision_pct":  0.00,   # TBD — update when S-1/A filed
    "underwriter_tier":          1.0,    # Top-tier assumed
    "concurrent_ipo_count":      2.0,    # Estimate
    "psex_30d_return":           0.00,   # UPDATE LIVE before prediction
    "vix_on_pricing_day":       18.0,    # UPDATE LIVE before prediction
    "pe_ratio":                 37.5,    # ₱669B cap / ₱17.8B NTM NI
    "ev_revenue_multiple_at_ipo": 7.44,  # ₱669B / ₱90B NTM revenue
    "mau_millions":             40.4,
    "profitable_flag":           1.0,
    "em_market_flag":            1.0,
    "dual_class_flag":           0.0,
}


def predict_gcash(
    psex_30d_return: float = 0.02,
    vix: float = 18.0,
    price_revision_pct: float = 0.00,
) -> dict:
    """
    Run the trained model to predict GCash Day-1 pop probability and expected return.

    Args:
        psex_30d_return:    PSEi 30-day trailing return (live, fetched at runtime)
        vix:                VIX index on pricing day (live)
        price_revision_pct: S-1/A price range revision delta (update when known)

    Returns:
        dict with pop_probability, expected_day1_return, confidence, feature_importances.
    """
    if not MODEL_PATH.exists():
        logger.info("Model not found — training on synthetic data first...")
        train_classifier()

    models = joblib.load(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)

    features = GCASH_FEATURES.copy()
    features["psex_30d_return"]       = psex_30d_return
    features["vix_on_pricing_day"]    = vix
    features["price_range_revision_pct"] = price_revision_pct

    X = pd.DataFrame([features])[FEATURE_COLS]
    X_scaled = scaler.transform(X)

    pop_prob         = float(models["classifier"].predict_proba(X_scaled)[0][1])
    expected_return  = float(models["regressor"].predict(X_scaled)[0])
    importances      = dict(zip(FEATURE_COLS, models["classifier"].feature_importances_))
    top_features     = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "pop_probability":      round(pop_prob * 100, 1),       # 0–100%
        "expected_day1_return": round(expected_return * 100, 1), # percent
        "confidence":           "High" if pop_prob > 0.70 or pop_prob < 0.30 else "Medium",
        "signal":               "Bullish" if pop_prob > 0.55 else ("Bearish" if pop_prob < 0.40 else "Neutral"),
        "top_features":         top_features,
        "inputs_used":          {k: features[k] for k in ["psex_30d_return", "vix_on_pricing_day", "price_range_revision_pct"]},
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("\n=== Training IPO Classifier (synthetic data) ===")
    metrics = train_classifier()
    print(f"AUC: {metrics['auc']}")
    print(f"Day-1 Return MAE: {metrics['mae_day1_return']}")

    print("\n=== GCash Day-1 Prediction ===")
    result = predict_gcash(psex_30d_return=0.03, vix=17.5, price_revision_pct=0.00)
    print(f"Day-1 Pop Probability: {result['pop_probability']}%")
    print(f"Expected Day-1 Return: {result['expected_day1_return']:+.1f}%")
    print(f"Signal: {result['signal']} ({result['confidence']} confidence)")
    print(f"\nTop 5 Features Driving Prediction:")
    for feat, imp in result["top_features"]:
        print(f"  {feat:<35} {imp:.3f}")
