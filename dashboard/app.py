"""Fraud Pattern Evolution Tracker -- Streamlit dashboard.

100% synthetic transaction data with injected fraud rings (see
docs/methodology_fraud_pattern.md). Ground truth exists here (unlike most
fraud demos), so model_evaluation numbers below are genuinely meaningful.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import text

from shared.database import get_engine

st.set_page_config(page_title="Fraud Pattern Evolution Tracker", layout="wide")
st.title("🕸️ Fraud Pattern Evolution Tracker")
st.caption(
    "100% synthetic transactions with injected fraud rings -- see "
    "docs/methodology_fraud_pattern.md. Ground truth is known by "
    "construction, so the model evaluation metrics below are real, not illustrative."
)


@st.cache_data(ttl=300)
def load(query: str) -> pd.DataFrame:
    engine = get_engine()
    return pd.read_sql(text(query), engine)


try:
    trends = load("SELECT * FROM fraud_pattern.fraud_trends ORDER BY month")
    evaluation = load("SELECT * FROM fraud_pattern.model_evaluation")
    alerts = load(
        "SELECT a.*, t.amount, t.merchant_category FROM fraud_pattern.alerts a "
        "JOIN fraud_pattern.transactions t ON t.transaction_id = a.transaction_id "
        "ORDER BY a.created_at DESC LIMIT 500"
    )
    graph_metrics = load("SELECT * FROM fraud_pattern.graph_metrics WHERE is_ring_candidate ORDER BY component_size DESC")
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not connect to the analytics database: {exc}")
    st.stop()

if trends.empty:
    st.warning(
        "No data yet. Trigger the `fraud_pattern_pipeline` DAG in Airflow "
        "(http://localhost:8081) and wait for it to complete, then refresh."
    )
    st.stop()

col1, col2, col3, col4 = st.columns(4)
if not evaluation.empty:
    ev = evaluation.iloc[0]
    col1.metric("Precision", f"{ev['precision']:.2f}")
    col2.metric("Recall", f"{ev['recall']:.2f}")
    col3.metric("F1", f"{ev['f1']:.2f}")
    col4.metric("ROC-AUC", f"{ev['roc_auc']:.2f}")

st.subheader("Fraud rate over time")
fig_trend = px.line(trends, x="month", y="fraud_rate", markers=True, title="Monthly fraud rate (ground truth)")
st.plotly_chart(fig_trend, use_container_width=True)

fig_amount = px.bar(trends, x="month", y=["total_amount", "fraud_amount"], barmode="overlay", title="Transaction volume vs. fraud volume ($)")
st.plotly_chart(fig_amount, use_container_width=True)

st.subheader("Connected-account clusters (shared device/IP)")
if not graph_metrics.empty:
    st.dataframe(
        graph_metrics[["account_id", "component_id", "component_size", "degree"]]
        .rename(columns={"account_id": "Account", "component_id": "Cluster ID", "component_size": "Cluster size", "degree": "Connections"}),
        use_container_width=True, hide_index=True,
    )
else:
    st.info("No multi-account clusters detected.")

st.subheader("Recent explainable alerts")
severity_options = sorted(alerts["severity"].unique().tolist()) if not alerts.empty else []
selected_severity = st.multiselect("Severity", options=severity_options, default=severity_options)
alerts_f = alerts[alerts["severity"].isin(selected_severity)] if selected_severity else alerts.iloc[0:0]
st.dataframe(
    alerts_f[["transaction_id", "account_id", "reason", "severity", "amount", "merchant_category"]]
    .rename(columns={"transaction_id": "Transaction", "account_id": "Account", "reason": "Reason", "severity": "Severity", "amount": "Amount", "merchant_category": "Merchant"}),
    use_container_width=True, hide_index=True,
)

with st.expander("Methodology & limitations"):
    st.markdown(
        """
        - **All data is synthetic**, with known ground truth (15 injected fraud rings + ~0.4%
          organic fraud) -- see `docs/methodology_fraud_pattern.md`.
        - Anomaly detection (IsolationForest) never sees the fraud label during training --
          evaluation against it afterward is a fair test.
        - Alerts are rule-based and explainable, combining the anomaly score with the graph
          (shared-device/IP cluster) signal.
        - Ring detection depends on shared device/IP reuse -- a ring that never reuses
          infrastructure would not be caught here.
        """
    )
