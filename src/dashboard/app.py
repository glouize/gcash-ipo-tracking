"""
src/dashboard/app.py
─────────────────────
GCash IPO Tracker — 5-Page Streamlit Dashboard
Run with: streamlit run src/dashboard/app.py
"""

import sys
from pathlib import Path

# Make sure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import date, datetime
import streamlit as st

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="GCash IPO Tracker",
    page_icon="💚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Lazy imports (avoid slow loads on every rerun) ────────────────────────────
@st.cache_data(ttl=60)
def load_gcash_quote():
    from src.ingestion.market_data import get_gcash_stock_quote
    return get_gcash_stock_quote()


@st.cache_data(ttl=3600)
def load_static_data():
    from src.ingestion.pse_edge_scraper import get_gcash_static, compute_revenue_growth
    data = get_gcash_static()
    data["revenue_growth"] = compute_revenue_growth(data["financials"])
    return data


@st.cache_data(ttl=3600)
def load_valuation():
    from src.analytics.valuation import run_all_methods
    from src.ingestion.market_data import fetch_peer_info, compute_peer_medians
    from src.storage.database import write_valuation, write_peer_comps
    peers = fetch_peer_info()
    medians = compute_peer_medians(peers) if not peers.empty else {}
    ev_rev = medians.get("median_ev_revenue", 5.5) or 5.5
    pe     = medians.get("median_pe_ratio",   28.0) or 28.0
    val_res = run_all_methods(peer_ev_revenue=float(ev_rev), peer_pe=float(pe))
    try:
        write_valuation(val_res, peer_ev_revenue=float(ev_rev), peer_pe=float(pe))
        write_peer_comps(peers)
    except Exception:
        pass
    return val_res, peers


@st.cache_data(ttl=1800)
def load_macro():
    from src.ingestion.market_data import get_vix_latest, get_psex_30d_return
    from src.ingestion.fx_rates import get_php_usd_rate
    from src.storage.database import write_macro
    macro_data = {
        "vix":          get_vix_latest() or 18.0,
        "psex_30d":     get_psex_30d_return() or 0.0,
        "php_usd_rate": get_php_usd_rate(),
    }
    try:
        write_macro(macro_data["vix"], macro_data["psex_30d"], macro_data["php_usd_rate"])
    except Exception:
        pass
    return macro_data


@st.cache_data(ttl=900)
def load_prediction(psex_30d, vix):
    from src.analytics.classifier import predict_gcash, train_classifier, MODEL_PATH
    from src.storage.database import write_prediction
    if not MODEL_PATH.exists():
        train_classifier()
    pred = predict_gcash(psex_30d_return=psex_30d, vix=vix)
    try:
        write_prediction(pred, psex_input=psex_30d, vix_input=vix)
    except Exception:
        pass
    return pred


@st.cache_data(ttl=1800)
def load_lifecycle():
    from src.analytics.lifecycle import (
        get_lifecycle_events, get_current_phase,
        days_to_listing, days_to_lockup_expiry, compute_lockup_overhang
    )
    return {
        "events":          get_lifecycle_events(),
        "current_phase":   get_current_phase(),
        "days_to_listing": days_to_listing(),
        "days_to_lockup":  days_to_lockup_expiry(),
        "overhang":        compute_lockup_overhang(),
    }


@st.cache_data(ttl=600)
def load_risk_flags():
    from src.analytics.risk_flags import get_all_flags, compute_risk_score
    return get_all_flags(), compute_risk_score()


@st.cache_data(ttl=1800)
def load_sentiment():
    from src.ingestion.sentiment import fetch_news_sentiment, fetch_google_trends, build_daily_sentiment
    from src.storage.database import write_sentiment
    news   = fetch_news_sentiment(days_back=14)
    trends = fetch_google_trends()
    daily  = build_daily_sentiment(days_back=14)
    try:
        if not daily.empty:
            write_sentiment(daily)
    except Exception:
        pass
    return news, trends, daily


# ── CSS Styling ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #1e3a5f 0%, #0d2137 100%);
        border-radius: 12px; padding: 16px; margin: 6px 0;
        border-left: 4px solid #00b0ff;
    }
    .metric-value { font-size: 1.8rem; font-weight: 700; color: #00e5ff; }
    .metric-label { font-size: 0.78rem; color: #90caf9; text-transform: uppercase; letter-spacing: 1px; }
    .flag-critical { background: #4a1515; border-left: 4px solid #f44336; border-radius: 8px; padding: 10px; margin: 6px 0; }
    .flag-warning  { background: #3d2e00; border-left: 4px solid #ff9800; border-radius: 8px; padding: 10px; margin: 6px 0; }
    .flag-ok       { background: #0a2e0a; border-left: 4px solid #4caf50; border-radius: 8px; padding: 10px; margin: 6px 0; }
    .flag-info     { background: #0d2137; border-left: 4px solid #2196f3; border-radius: 8px; padding: 10px; margin: 6px 0; }
    .phase-badge   { background: #00b0ff22; border: 1px solid #00b0ff; border-radius: 20px;
                     padding: 4px 14px; font-size: 0.85rem; color: #00e5ff; display: inline-block; }
    .stTabs [data-baseweb="tab"] { font-size: 0.92rem; font-weight: 600; }
</style>
""", unsafe_allow_html=True)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/7/73/GCash_logo.svg/240px-GCash_logo.svg.png",
             width=120)
    st.title("GCash IPO Tracker")
    st.caption("Mynt Inc. · PSE: GCASH")
    st.divider()

    quote = load_gcash_quote()
    st.markdown("### 🔴 LIVE MARKET QUOTE")
    st.metric(
        label="PSE: GCASH",
        value=f"₱{quote['current_price']:.2f}",
        delta=f"{quote['day_change']:+.2f} ({quote['day_change_pct']:+.2f}% today)",
    )
    st.caption(
        f"**IPO:** ₱{quote['ipo_price']:.2f} · **Net:** {quote['gain_since_ipo_pct']:+.1f}% · **Day:** ₱{quote['day_low']:.2f}–₱{quote['day_high']:.2f}"
    )
    st.divider()

    lc = load_lifecycle()
    st.metric("Days to Listing", lc["days_to_listing"], help="Oct 20, 2026")
    st.metric("Days to Lockup Expiry", lc["days_to_lockup"], help="Apr 20, 2027")

    st.divider()
    macro = load_macro()
    rate = macro["php_usd_rate"]
    st.metric("PHP/USD Rate", f"₱{rate:.2f}", help="BSP or yfinance")
    st.metric("VIX", f"{macro['vix']:.1f}", help="Fear index; <20 = calm market")
    st.metric("PSEi 30d Return", f"{macro['psex_30d']*100:+.1f}%")

    st.divider()
    if st.button("🔄 Refresh All Data"):
        st.cache_data.clear()
        st.rerun()

    st.caption(f"Last updated: {datetime.now().strftime('%H:%M PHT')}")


# ── Main Tabs ─────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📋 Overview",
    "💰 Valuation",
    "🤖 ML Prediction",
    "📡 Sentiment",
    "🗓 Lifecycle Monitor",
    "💾 Staging & CSV Export",
])


# ═════════════════════════════════════════════════════════════════════════════
# TAB 1 — Overview
# ═════════════════════════════════════════════════════════════════════════════
with tab1:
    data = load_static_data()
    flags, risk_score = load_risk_flags()
    lc = load_lifecycle()

    st.markdown(f"## Globe Fintech Innovations, Inc. (Mynt)")
    st.markdown(
        f'<span class="phase-badge">📍 {lc["current_phase"]}</span>',
        unsafe_allow_html=True
    )

    st.divider()

    # ── Live Stock Quote Banner ───────────────────────────────────────────────
    quote = load_gcash_quote()
    st.markdown("### 📈 Live Stock Value & Market Performance (PSE: GCASH)")
    qcol1, qcol2, qcol3, qcol4, qcol5 = st.columns(5)
    with qcol1:
        st.metric(
            "Current Stock Price",
            f"₱{quote['current_price']:.2f}",
            delta=f"{quote['day_change']:+.2f} ({quote['day_change_pct']:+.2f}% today)",
        )
    with qcol2:
        st.metric(
            "Gain Since IPO (₱6.60)",
            f"{quote['gain_since_ipo_pct']:+.2f}%",
            delta=f"₱{quote['gain_since_ipo']:+.2f}/sh",
        )
    with qcol3:
        st.metric(
            "Day Range",
            f"₱{quote['day_low']:.2f} – ₱{quote['day_high']:.2f}",
            help=f"Open: ₱{quote['day_open']:.2f} · Prev Close: ₱{quote['prev_close']:.2f}",
        )
    with qcol4:
        st.metric(
            "Live Market Cap",
            f"₱{quote['market_cap_php_bn']:.1f}B",
            help=f"~${quote['market_cap_usd_bn']:.2f}B USD",
        )
    with qcol5:
        st.metric(
            "Volume Traded",
            f"{quote['day_volume_m']}M shs",
            help=f"Traded Value: ~₱{quote['day_value_m']}M",
        )

    # ── Post-Listing Stock Price Chart ────────────────────────────────────────
    df_hist = quote["history"]
    fig_stock = go.Figure()
    fig_stock.add_trace(go.Candlestick(
        x=df_hist["date"],
        open=df_hist["open"],
        high=df_hist["high"],
        low=df_hist["low"],
        close=df_hist["close"],
        name="PSE: GCASH",
        increasing_line_color="#00e676",
        decreasing_line_color="#f44336",
    ))
    fig_stock.add_hline(
        y=quote["ipo_price"],
        line_dash="dash",
        line_color="#00e5ff",
        annotation_text="IPO Offer Price (₱6.60)",
        annotation_position="bottom right",
    )
    fig_stock.add_hline(
        y=quote["all_time_high"],
        line_dash="dot",
        line_color="#ffb300",
        annotation_text=f"Listing High (₱{quote['all_time_high']:.2f})",
        annotation_position="top right",
    )
    fig_stock.update_layout(
        title="PSE: GCASH — Post-Listing Daily Price History (Stabilization Window)",
        template="plotly_dark",
        height=320,
        xaxis_rangeslider_visible=False,
        yaxis=dict(title="Stock Price (PHP ₱)", tickprefix="₱"),
        margin=dict(t=40, b=20, l=40, r=40),
    )
    st.plotly_chart(fig_stock, use_container_width=True)

    st.divider()

    # ── Key IPO Facts ─────────────────────────────────────────────────────────
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Final IPO Price", "₱6.60", help="Final offer price determined via bookbuilding (filing ceiling: ₱10.00)")
        st.metric("Analyst Target", "₱7.50–₱8.50")
    with col2:
        st.metric("Total Raised", "₱60.9B", help="Including overallotment (target ceiling was ₱92.3B)")
        st.metric("Market Cap at Listing", "₱441.5B (~$7.0B USD)")
    with col3:
        st.metric("Public Float", "12%", delta="⚠️ Below 15% standard")
        st.metric("Total Shares", "66.9B fully diluted")
    with col4:
        st.metric("Offer Period", "Oct 6–12, 2026")
        st.metric("Listing Date", "Oct 20, 2026")
    with col5:
        st.metric("2025 Revenue", "₱79.7B")
        st.metric("2025 Net Income", "₱17.2B")

    st.divider()

    # ── Revenue History Chart ─────────────────────────────────────────────────
    col_a, col_b = st.columns([2, 1])
    with col_a:
        st.subheader("Revenue & Net Income History")
        fin = data["financials"]
        years   = [2023, 2024, 2025]
        revs    = [fin[y]["revenue_php_bn"]   for y in years]
        incomes = [fin[y]["net_income_php_bn"] for y in years]
        margins = [fin[y]["net_margin"] * 100  for y in years]

        fig = go.Figure()
        fig.add_bar(name="Revenue (₱B)", x=years, y=revs, marker_color="#00b0ff", opacity=0.8)
        fig.add_bar(name="Net Income (₱B)", x=years, y=incomes, marker_color="#00e676", opacity=0.8)
        fig.add_trace(go.Scatter(
            name="Net Margin %", x=years, y=margins,
            yaxis="y2", mode="lines+markers",
            line=dict(color="#ff9800", width=2), marker=dict(size=8)
        ))
        fig.update_layout(
            template="plotly_dark", barmode="group",
            yaxis=dict(title="₱ Billion"),
            yaxis2=dict(title="Net Margin %", overlaying="y", side="right", ticksuffix="%"),
            legend=dict(orientation="h", y=1.1),
            height=380, margin=dict(t=30, b=20),
        )
        # Revenue growth annotations
        growth = data["revenue_growth"]
        for i, yr in enumerate([2024, 2025]):
            if yr in growth:
                fig.add_annotation(
                    x=yr, y=revs[i],
                    text=f"+{growth[yr]*100:.0f}% YoY",
                    showarrow=False, yshift=18,
                    font=dict(color="#00e5ff", size=11)
                )
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.subheader("Shareholder Structure")
        sh = data["shareholders"]
        fig2 = go.Figure(go.Pie(
            labels=list(sh.keys()),
            values=list(sh.values()),
            hole=0.45,
            marker=dict(colors=["#00b0ff", "#f44336", "#ff9800", "#4caf50", "#9c27b0"]),
            textinfo="label+percent",
        ))
        fig2.update_layout(
            template="plotly_dark", height=380,
            margin=dict(t=10, b=10, l=10, r=10),
            showlegend=False,
        )
        st.plotly_chart(fig2, use_container_width=True)

        st.caption("⚠️ 80% of IPO is secondary shares from these holders")

    st.divider()

    # ── Risk Flags Summary ────────────────────────────────────────────────────
    st.subheader(f"Risk Assessment — Score: {risk_score['score']}/100 ({risk_score['label']})")

    severity_filter = st.multiselect(
        "Filter by severity:",
        ["🚨 Critical", "⚠️ Warning", "✅ Clear", "ℹ️ Info"],
        default=["🚨 Critical", "⚠️ Warning"],
    )

    for f in flags:
        if f.severity.value not in severity_filter:
            continue
        css_class = {
            "🚨 Critical": "flag-critical",
            "⚠️ Warning":  "flag-warning",
            "✅ Clear":    "flag-ok",
            "ℹ️ Info":    "flag-info",
        }.get(f.severity.value, "flag-info")

        st.markdown(
            f'<div class="{css_class}">'
            f'<strong>{f.severity.value} [{f.id}] {f.name}</strong><br/>'
            f'<small>{f.description}</small>'
            f'</div>',
            unsafe_allow_html=True
        )


# ═════════════════════════════════════════════════════════════════════════════
# TAB 2 — Valuation
# ═════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("5-Method Fair Value Triangulation")
    st.caption("All values in Philippine Peso (₱). Peer multiples updated from live market data.")

    with st.spinner("Fetching peer comps & running valuation models..."):
        val_df, peers_df = load_valuation()

    # Fair value table
    st.dataframe(
        val_df.style
            .highlight_max(subset=["Mid (₱)"], color="#1a3a1a")
            .format({"Low (₱)": "₱{:.2f}", "Mid (₱)": "₱{:.2f}", "High (₱)": "₱{:.2f}"}),
        use_container_width=True, height=280
    )

    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        # Fair value range bar chart
        st.subheader("Fair Value Range vs. Offer Price")
        methods = val_df["Method"].tolist()
        lows  = val_df["Low (₱)"].tolist()
        mids  = val_df["Mid (₱)"].tolist()
        highs = val_df["High (₱)"].tolist()

        fig = go.Figure()
        # Range bars (error bars)
        fig.add_trace(go.Scatter(
            name="Mid Estimate", x=methods, y=mids,
            mode="markers", marker=dict(size=12, color="#00e5ff"),
            error_y=dict(
                type="data",
                array=[h - m for h, m in zip(highs, mids)],
                arrayminus=[m - l for m, l in zip(mids, lows)],
                visible=True, color="#00b0ff"
            )
        ))
        # Reference lines
        quote = load_gcash_quote()
        for price, label, color in [
            (10.00, "Max Offer Ceiling (₱10)", "#f44336"),
            (8.00,  "Analyst Mid (₱8)", "#ff9800"),
            (7.50,  "Analyst Low (₱7.50)", "#ff9800"),
            (quote["current_price"], f"Current Price (₱{quote['current_price']:.2f})", "#e040fb"),
            (6.60,  "Final IPO Price (₱6.60)", "#00e676"),
        ]:
            fig.add_hline(y=price, line_dash="dash", line_color=color,
                          annotation_text=label, annotation_position="right")

        fig.update_layout(
            template="plotly_dark", height=400,
            xaxis_tickangle=-30,
            yaxis=dict(title="₱ per Share", range=[4, 12]),
            margin=dict(t=10, b=80),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # Peer comps table
        st.subheader("Peer Comparable Companies")
        if not peers_df.empty:
            display_cols = ["ticker", "name", "ev_revenue", "ps_ratio", "pe_ratio", "gross_margin"]
            available_cols = [c for c in display_cols if c in peers_df.columns]
            display_df = peers_df[available_cols].copy()

            if "gross_margin" in display_df.columns:
                display_df["gross_margin"] = display_df["gross_margin"].apply(
                    lambda x: f"{x*100:.1f}%" if pd.notna(x) else "N/A"
                )
            display_df = display_df.rename(columns={
                "ticker": "Ticker", "name": "Company",
                "ev_revenue": "EV/Rev", "ps_ratio": "P/S",
                "pe_ratio": "P/E", "gross_margin": "Gross Margin"
            })
            st.dataframe(display_df, use_container_width=True, height=300)
        else:
            st.info("Peer data loading... (yfinance may be rate-limited)")

        # Key valuation insight
        consensus_row = val_df[val_df["Method"].str.contains("CONSENSUS")]
        if not consensus_row.empty:
            c_low  = consensus_row["Low (₱)"].iloc[0]
            c_mid  = consensus_row["Mid (₱)"].iloc[0]
            c_high = consensus_row["High (₱)"].iloc[0]
            st.info(
                f"**Consensus Fair Value: ₱{c_low:.2f} – ₱{c_high:.2f}** (mid: ₱{c_mid:.2f})\n\n"
                f"At ₱10/share (max), GCash would trade at a premium to our mid consensus. "
                f"Analyst target (₱7.50–₱8.50) aligns with our model."
            )


# ═════════════════════════════════════════════════════════════════════════════
# TAB 3 — ML Prediction
# ═════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("Day-1 Pop Prediction — XGBoost Classifier")

    macro = load_macro()
    col_inp1, col_inp2, col_inp3 = st.columns(3)
    with col_inp1:
        vix_input  = st.number_input("VIX on Pricing Day", min_value=10.0, max_value=50.0,
                                     value=float(round(macro["vix"], 1)), step=0.5)
    with col_inp2:
        psex_input = st.number_input("PSEi 30d Return (%)", min_value=-30.0, max_value=30.0,
                                     value=float(round(macro["psex_30d"] * 100, 1)), step=0.5)
    with col_inp3:
        rev_input  = st.number_input("Price Range Revision (%)", min_value=-20.0, max_value=30.0,
                                     value=0.0, step=0.5,
                                     help="% change in offer price midpoint (S-1/A vs initial S-1). Fill in when known.")

    with st.spinner("Running prediction model..."):
        pred = load_prediction(psex_input / 100.0, vix_input)

    st.divider()
    col1, col2, col3 = st.columns(3)

    with col1:
        # Gauge: Day-1 Pop Probability
        pop_prob = pred["pop_probability"]
        color = "#4caf50" if pop_prob > 60 else ("#ff9800" if pop_prob > 40 else "#f44336")
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=pop_prob,
            title={"text": "Day-1 Pop >10% Probability", "font": {"size": 14}},
            number={"suffix": "%", "font": {"size": 32, "color": color}},
            gauge={
                "axis":  {"range": [0, 100], "tickwidth": 1},
                "bar":   {"color": color},
                "steps": [
                    {"range": [0,  40], "color": "#4a1515"},
                    {"range": [40, 60], "color": "#3d2e00"},
                    {"range": [60, 100], "color": "#0a2e0a"},
                ],
                "threshold": {"line": {"color": "white", "width": 3}, "value": 60},
            }
        ))
        fig_gauge.update_layout(template="plotly_dark", height=280, margin=dict(t=30, b=10))
        st.plotly_chart(fig_gauge, use_container_width=True)

    with col2:
        st.metric("Expected Day-1 Return",
                  f"{pred['expected_day1_return']:+.1f}%",
                  delta=pred["signal"])
        st.metric("Model Confidence", pred["confidence"])
        st.metric("Prediction Signal", pred["signal"])

        st.caption(
            "Model trained on synthetic PSE + SEA IPO data (n=300). "
            "Update `data/training/pse_ipo_history.csv` with real historical data for improved accuracy."
        )

    with col3:
        st.subheader("Top Feature Importances")
        feat_names = [f[0].replace("_", " ").title() for f in pred["top_features"]]
        feat_vals  = [round(f[1] * 100, 1) for f in pred["top_features"]]
        fig_feat = go.Figure(go.Bar(
            x=feat_vals, y=feat_names,
            orientation="h",
            marker_color="#00b0ff",
        ))
        fig_feat.update_layout(
            template="plotly_dark", height=280,
            xaxis_title="Importance (%)",
            margin=dict(t=10, b=10, l=10, r=10),
        )
        st.plotly_chart(fig_feat, use_container_width=True)

    st.divider()
    st.subheader("Sensitivity Analysis")
    st.caption("How does the prediction change with different market conditions?")

    scenarios = {
        "PSEi -10% + VIX 30 (Bear Market)":     {"psex": -0.10, "vix": 30.0, "rev": 0.00},
        "Current Market (Baseline)":             {"psex": macro["psex_30d"], "vix": macro["vix"], "rev": 0.00},
        "PSEi +5% + VIX 15 (Bull Market)":      {"psex": 0.05,  "vix": 15.0, "rev": 0.00},
        "Offer Price Raised +10% (S-1/A)":       {"psex": macro["psex_30d"], "vix": macro["vix"], "rev": 0.10},
    }

    sa_rows = []
    for scen_name, params in scenarios.items():
        with st.spinner(f"Running: {scen_name}"):
            r = load_prediction(params["psex"], params["vix"])
        sa_rows.append({
            "Scenario": scen_name,
            "Pop Prob": f"{r['pop_probability']}%",
            "Exp. Day-1 Return": f"{r['expected_day1_return']:+.1f}%",
            "Signal": r["signal"],
        })
    st.dataframe(pd.DataFrame(sa_rows), use_container_width=True, hide_index=True)


# ═════════════════════════════════════════════════════════════════════════════
# TAB 4 — Sentiment
# ═════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("Market Sentiment — GCash IPO")

    with st.spinner("Fetching sentiment data..."):
        news_df, trends_df, daily_df = load_sentiment()

    col1, col2 = st.columns(2)

    with col1:
        # Google Trends
        st.subheader("Google Trends: 'GCash IPO' (Philippines)")
        if not trends_df.empty:
            fig_trends = px.area(
                trends_df, x="date", y="interest_score",
                color_discrete_sequence=["#00b0ff"],
                template="plotly_dark",
            )
            fig_trends.update_layout(height=300, margin=dict(t=10, b=20))
            st.plotly_chart(fig_trends, use_container_width=True)
        else:
            st.info("Google Trends data unavailable (rate limiting). Try again later.")

    with col2:
        # Daily sentiment score
        st.subheader("Daily Sentiment Score (Reddit + News)")
        if not daily_df.empty:
            daily_df["date"] = pd.to_datetime(daily_df["date"])
            colors = daily_df["avg_compound"].apply(
                lambda x: "#4caf50" if x > 0.05 else ("#f44336" if x < -0.05 else "#ff9800")
            )
            fig_sent = go.Figure(go.Bar(
                x=daily_df["date"], y=daily_df["avg_compound"],
                marker_color=colors, name="Sentiment Score"
            ))
            fig_sent.add_hline(y=0.05, line_dash="dash", line_color="#4caf50",
                               annotation_text="Bullish threshold")
            fig_sent.add_hline(y=-0.05, line_dash="dash", line_color="#f44336",
                               annotation_text="Bearish threshold")
            fig_sent.update_layout(
                template="plotly_dark", height=300,
                yaxis=dict(title="VADER Compound Score", range=[-1, 1]),
                margin=dict(t=10, b=20),
            )
            st.plotly_chart(fig_sent, use_container_width=True)
        else:
            st.info("No sentiment data yet. Configure Reddit credentials in .env to enable real-time scoring.")

    st.divider()

    # News feed
    st.subheader("Latest News Articles (GCash / Mynt)")
    if not news_df.empty:
        for _, row in news_df.head(10).iterrows():
            sentiment_color = {"Bullish": "🟢", "Bearish": "🔴", "Neutral": "🟡"}.get(
                row.get("sentiment", ""), "⚪"
            )
            st.markdown(
                f"{sentiment_color} **[{row.get('title', 'Untitled')}]({row.get('url', '#')})**  \n"
                f"<small>{row.get('source', '')} · {str(row.get('date', ''))[:10]}</small>",
                unsafe_allow_html=True
            )
    else:
        st.info(
            "No GCash articles detected in RSS feeds yet. "
            "This will populate automatically as coverage increases closer to listing."
        )

    # Macro overlay
    st.divider()
    macro = load_macro()
    st.subheader("Macro Context")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("VIX", f"{macro['vix']:.1f}",
                  delta="Market calm" if macro["vix"] < 20 else "Elevated volatility",
                  delta_color="normal" if macro["vix"] < 20 else "inverse")
    with c2:
        st.metric("PSEi 30d Return", f"{macro['psex_30d']*100:+.1f}%",
                  delta_color="normal")
    with c3:
        st.metric("PHP/USD", f"₱{macro['php_usd_rate']:.2f}",
                  help="Weaker PHP (higher number) increases USD-denominated investor costs")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 5 — Lifecycle Monitor
# ═════════════════════════════════════════════════════════════════════════════
with tab5:
    st.subheader("GCash IPO Lifecycle Monitor")
    lc = load_lifecycle()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Current Phase", lc["current_phase"])
    with col2:
        delta_color = "normal" if lc["days_to_listing"] > 0 else "off"
        st.metric("Days to Listing",
                  lc["days_to_listing"] if lc["days_to_listing"] > 0 else "LISTED!",
                  delta="Oct 20, 2026")
    with col3:
        st.metric("Lockup Overhang Ratio", f"{lc['overhang']:.1f}×",
                  delta="⚠️ Very High (>7×)", delta_color="inverse")

    st.divider()

    # Timeline table
    st.subheader("Full Event Timeline")
    timeline_rows = []
    for e in lc["events"]:
        status = "✅ Past" if e.is_past else ("📍 Today" if e.is_today else f"⏳ In {e.days_away}d")
        timeline_rows.append({
            "Status":       status,
            "Date":         e.date.strftime("%b %d, %Y"),
            "Phase":        e.phase,
            "Event":        e.name,
            "Description":  e.description[:100] + "..." if len(e.description) > 100 else e.description,
        })
    timeline_df = pd.DataFrame(timeline_rows)
    st.dataframe(timeline_df, use_container_width=True, hide_index=True, height=420)

    st.divider()

    # Lockup countdown
    st.subheader("⚠️ Lockup Expiry Risk Monitor")
    st.info(
        f"**Lockup Expires: April 20, 2027 ({lc['days_to_lockup']} days away)**\n\n"
        f"When the lockup expires, Globe Telecom (~45%), Ant Group (~33%), Ayala (~10%), "
        f"and MUFG (~5%) can begin selling shares.\n\n"
        f"**Lockup Overhang Ratio: {lc['overhang']:.1f}× float**  \n"
        f"For every 1 share in public float, there are {lc['overhang']:.1f} locked shares waiting to be sold. "
        f"This is a significant supply shock risk. Historical data shows stocks with overhang >5× "
        f"underperform peers by ~15–25% in the 30 days following lockup expiry."
    )

    # Lockup countdown bar
    listing_date = date(2026, 10, 20)
    lockup_date  = date(2027,  4, 20)
    today        = date.today()
    total_lockup_days   = (lockup_date - listing_date).days
    elapsed_lockup_days = max(0, (today - listing_date).days)
    pct_elapsed         = min(1.0, elapsed_lockup_days / total_lockup_days) if total_lockup_days > 0 else 0

    st.markdown(f"**Lockup Period Progress:** {elapsed_lockup_days}/{total_lockup_days} days elapsed")
    st.progress(pct_elapsed, text=f"{'%.1f' % (pct_elapsed*100)}% through lockup period")

    # Alert configuration reminder
    st.divider()
    st.subheader("⚙️ Alert Configuration")
    webhook_configured = bool(__import__("os").getenv("DISCORD_WEBHOOK_URL"))
    if webhook_configured:
        st.success("✅ Discord webhook configured — alerts are active.")
    else:
        st.warning(
            "⚠️ Discord webhook not configured.  \n"
            "Add `DISCORD_WEBHOOK_URL=...` to your `.env` file to receive automated alerts for:\n"
            "- New PSE EDGE disclosures\n"
            "- Offer period open/close (Oct 6 & 12)\n"
            "- Listing Day countdown (Oct 20)\n"
            "- Lockup expiry warnings (Apr 13 & 19)"
        )


# ═════════════════════════════════════════════════════════════════════════════
# TAB 6 — Data Staging & Export
# ═════════════════════════════════════════════════════════════════════════════
with tab6:
    st.subheader("💾 SQLite Staging Layer & Incremental ETL Pipeline")
    st.caption("Full extraction from sources with intelligent incremental delta loading (CDC), MD5 record-hash fingerprinting, and CSV exports.")

    from src.storage.database import (
        get_db_summary, read_table, export_all_to_csv,
        run_full_pipeline_incremental_load, get_audit_log, get_watermarks,
        write_valuation, write_peer_comps, write_macro,
        write_sentiment, write_prediction, DB_PATH, EXPORT_DIR
    )

    # Database connection status card
    db_size_kb = (DB_PATH.stat().st_size / 1024) if DB_PATH.exists() else 0
    c_stat1, c_stat2, c_stat3, c_stat4 = st.columns(4)
    with c_stat1:
        st.metric("Database Engine", "SQLite (WAL mode)")
    with c_stat2:
        st.metric("DB File Size", f"{db_size_kb:.1f} KB")
    with c_stat3:
        st.metric("Storage Location", "data/gcash_staging.db")
    with c_stat4:
        st.metric("CSV Export Target", "data/exports/")

    st.divider()

    # ── Full Extract & Incremental Load Controls ──────────────────────────────
    st.subheader("⚡ Full Extract & Incremental ETL Pipeline")
    st.caption("Pulls a complete full shot from live source APIs / models, compares record fingerprints (MD5), and only commits new or changed records to staging.")

    col_ctrl1, col_ctrl2 = st.columns([3, 1])
    with col_ctrl1:
        force_reload = st.checkbox(
            "Force Full Reload (bypass incremental deduplication)",
            value=False,
            help="If checked, ignores existing record hashes and inserts all incoming source records."
        )
    with col_ctrl2:
        run_etl = st.button("🚀 Run Incremental Pipeline", type="primary", use_container_width=True)

    if run_etl:
        with st.spinner("Extracting full shot from sources and running incremental load..."):
            pipeline_results = run_full_pipeline_incremental_load(force_full=force_reload)
            st.success("✅ Incremental ETL pipeline run finished!")

            # Summary metrics of the run
            res_df = pd.DataFrame(pipeline_results).rename(columns={
                "entity": "Entity / Domain",
                "read": "Source Extracted (Full Shot)",
                "inserted": "New Inserted (Deltas)",
                "skipped": "Skipped (Unchanged Duplicates)",
            })
            st.dataframe(res_df, use_container_width=True, hide_index=True)

    st.divider()

    # ── Staging Summary Table ─────────────────────────────────────────────────
    col_sum1, col_sum2 = st.columns(2)
    with col_sum1:
        st.subheader("Staging Tables Summary")
        summary = get_db_summary()
        summary_rows = []
        for table_name, stats in summary.items():
            summary_rows.append({
                "Table Name": table_name,
                "Total Records": stats["rows"],
                "First Recorded": stats["first_date"] or "—",
                "Latest Recorded": stats["last_date"] or "—",
            })
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    with col_sum2:
        st.subheader("ETL Watermarks")
        watermarks_df = get_watermarks()
        if not watermarks_df.empty:
            st.dataframe(watermarks_df.rename(columns={
                "entity_name": "Entity",
                "last_loaded_at": "Last Loaded",
                "last_record_count": "Last Batch Count",
                "last_status": "Status"
            }), use_container_width=True, hide_index=True)
        else:
            st.info("No watermark entries yet. Run the incremental pipeline above to populate.")

    st.divider()

    # ── Table / View Explorer ─────────────────────────────────────────────────
    st.subheader("🔍 Inspect Staging Tables, Views & Audit Logs")
    available_tables = [
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
    selected_table = st.selectbox("Select table or view to inspect:", available_tables, index=0)

    df_view = read_table(selected_table)
    col_vw1, col_vw2 = st.columns([3, 1])
    with col_vw1:
        st.caption(f"Showing **{len(df_view)}** records from `{selected_table}`")
    with col_vw2:
        csv_data = df_view.to_csv(index=False).encode("utf-8")
        st.download_button(
            label=f"📥 Download {selected_table}.csv",
            data=csv_data,
            file_name=f"gcash_{selected_table}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.dataframe(df_view, use_container_width=True, height=320)

    st.divider()

    # ── Bulk CSV Export ───────────────────────────────────────────────────────
    st.subheader("📦 Bulk CSV Export to Disk")
    st.caption("Exports all staging tables, analytical views, and audit logs simultaneously into `data/exports/`.")

    if st.button("🚀 Export All Datasets to CSV", use_container_width=False):
        with st.spinner("Generating CSV files..."):
            exports = export_all_to_csv()
            st.success(f"✅ Successfully exported {len(exports)} CSV files to `data/exports/`!")
            exp_rows = []
            for name, path in exports.items():
                size_kb = path.stat().st_size / 1024 if path.exists() else 0
                exp_rows.append({
                    "Dataset": name,
                    "File Name": path.name,
                    "Size (KB)": f"{size_kb:.2f} KB",
                    "Path": str(path),
                })
            st.dataframe(pd.DataFrame(exp_rows), use_container_width=True, hide_index=True)


