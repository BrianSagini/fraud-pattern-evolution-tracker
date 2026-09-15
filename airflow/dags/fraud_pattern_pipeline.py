"""Fraud Pattern Evolution Tracker -- Airflow DAG.

100% synthetic transactions with injected fraud rings (see
projects/04_fraud_pattern_evolution/pipeline.py) -> validate -> load ->
graph analytics (connected accounts) -> unsupervised anomaly detection ->
model evaluation against synthetic ground truth -> explainable alerts ->
fraud trend SQL -> data-quality check.
"""
from __future__ import annotations

import os
import tempfile
from datetime import timedelta

import pandas as pd
import pendulum
from airflow.sdk import DAG, task

import pipeline
from shared.database import get_engine

TMP = tempfile.gettempdir()

with DAG(
    dag_id="fraud_pattern_pipeline",
    description="Generate synthetic transactions with fraud rings, run graph + anomaly detection, evaluate against ground truth",
    schedule="@daily",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=2),
        "execution_timeout": timedelta(minutes=30),
    },
    tags=["fraud", "graph", "project-04"],
) as dag:

    @task
    def ensure_schema() -> None:
        from shared.database import run_sql_file
        run_sql_file(os.path.join(os.path.dirname(pipeline.__file__), "sql", "001_schema.sql"))

    @task
    def generate_data() -> dict:
        accounts, transactions = pipeline.generate_transactions()
        accounts_path = os.path.join(TMP, "fraud_accounts.parquet")
        txn_path = os.path.join(TMP, "fraud_transactions_raw.parquet")
        accounts.to_parquet(accounts_path)
        transactions.to_parquet(txn_path)
        return {"accounts_path": accounts_path, "txn_path": txn_path}

    @task
    def validate_and_load(paths: dict) -> dict:
        accounts = pd.read_parquet(paths["accounts_path"])
        transactions = pd.read_parquet(paths["txn_path"])
        report = pipeline.validate_transactions(transactions)
        report.raise_if_invalid(max_invalid_ratio=0.001)
        clean_txns = transactions.drop(index=list(report.invalid_row_indices))

        accounts_loaded = pipeline.load_accounts(accounts)
        txns_loaded = pipeline.load_transactions(clean_txns)
        clean_path = os.path.join(TMP, "fraud_transactions_clean.parquet")
        clean_txns.to_parquet(clean_path)
        return {"accounts_loaded": accounts_loaded, "txns_loaded": txns_loaded, "clean_path": clean_path}

    @task
    def graph_analytics(load_result: dict) -> int:
        transactions = pd.read_parquet(load_result["clean_path"])
        metrics = pipeline.compute_graph_metrics(transactions)
        return pipeline.load_graph_metrics(metrics)

    @task
    def anomaly_detection(load_result: dict) -> int:
        transactions = pd.read_parquet(load_result["clean_path"])
        scores = pipeline.detect_anomalies(transactions)
        return pipeline.load_anomaly_scores(scores)

    @task
    def evaluate_model(_anomaly_rows: int) -> dict:
        return pipeline.evaluate_model_and_load()

    @task
    def generate_alerts(_graph_rows: int, _eval_result: dict) -> int:
        return pipeline.generate_explainable_alerts()

    @task
    def compute_trends(_txns_loaded: dict) -> int:
        return pipeline.compute_and_load_trends()

    @task
    def create_powerbi_views(_alerts: int, _trends: int) -> None:
        from shared.database import run_sql_file
        run_sql_file(os.path.join(os.path.dirname(pipeline.__file__), "sql", "005_powerbi_views.sql"))

    @task
    def data_quality_check(_views_done: None) -> None:
        engine = get_engine()
        with engine.connect() as conn:
            total_txns = conn.exec_driver_sql("SELECT COUNT(*) FROM fraud_pattern.transactions").scalar()
            eval_row = conn.exec_driver_sql(
                "SELECT precision, recall, f1, roc_auc FROM fraud_pattern.model_evaluation WHERE model_name = 'isolation_forest_v1'"
            ).first()
        if total_txns == 0:
            raise ValueError("fraud_pattern.transactions is empty after load")
        if eval_row is None:
            raise ValueError("model_evaluation row missing for isolation_forest_v1")
        if eval_row.roc_auc is None or eval_row.roc_auc < 0.5:
            raise ValueError(f"Anomaly model ROC-AUC ({eval_row.roc_auc}) is no better than random -- investigate")

    schema = ensure_schema()
    gen = generate_data()
    loaded = validate_and_load(gen)
    graph = graph_analytics(loaded)
    anomalies = anomaly_detection(loaded)
    evaluation = evaluate_model(anomalies)
    alerts = generate_alerts(graph, evaluation)
    trends = compute_trends(loaded)
    views = create_powerbi_views(alerts, trends)
    dq = data_quality_check(views)

    schema >> gen >> loaded >> [graph, anomalies]
    anomalies >> evaluation
    [graph, evaluation] >> alerts
    loaded >> trends
    [alerts, trends] >> views >> dq
