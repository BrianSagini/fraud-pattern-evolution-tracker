"""Fraud Pattern Evolution Tracker -- synthetic data + detection logic.

100% SYNTHETIC transaction data. Real labeled fraud datasets are either
gated behind a Kaggle competition account or under NDA in practice (see
docs/data_sources.md) -- a generator with injected fraud rings is used
instead. Crucially, because we control the ground truth here
(`is_fraud`/`is_fraud_ring_member`), the model-evaluation metrics
(precision/recall/F1/ROC-AUC) computed downstream are genuinely
meaningful, unlike most demo fraud projects that have no ground truth
to check anomaly scores against at all.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import networkx as nx
import numpy as np
import pandas as pd

from shared.database import bulk_upsert_dataframe, upsert_dataframe
from shared.validation import validate_dataframe

RNG_SEED = 7
N_ACCOUNTS = 5_000
N_MONTHS = 12
N_RINGS = 15
RING_SIZE_RANGE = (3, 8)
MERCHANT_CATEGORIES = ["Grocery", "Electronics", "Travel", "Restaurants", "Online Retail", "Utilities", "Gas Station", "Entertainment"]
ACCOUNT_TYPES = ["Checking", "Savings", "Credit Card"]

RAW_DIR = os.path.join(os.path.dirname(__file__), "data_raw")


def _generate_accounts(rng: np.random.Generator) -> pd.DataFrame:
    accounts = pd.DataFrame({
        "account_id": [f"A{100000+i}" for i in range(N_ACCOUNTS)],
        "account_type": rng.choice(ACCOUNT_TYPES, N_ACCOUNTS),
        "opened_date": pd.to_datetime("2023-01-01") + pd.to_timedelta(rng.integers(0, 700, N_ACCOUNTS), unit="D"),
        "home_country": rng.choice(["US", "GB", "CA", "AU", "DE"], N_ACCOUNTS, p=[0.6, 0.15, 0.1, 0.1, 0.05]),
    })
    accounts["is_fraud_ring_member"] = False
    accounts["ring_id"] = None
    return accounts


def _assign_fraud_rings(accounts: pd.DataFrame, rng: np.random.Generator) -> tuple[pd.DataFrame, dict]:
    """Pick disjoint sets of accounts to form fraud rings that share
    devices/IPs and transact with elevated velocity/amount -- the
    synthetic ground truth this whole project's evaluation rests on."""
    ring_devices = {}
    available = accounts["account_id"].sample(frac=1, random_state=RNG_SEED).tolist()
    idx = 0
    for ring_num in range(N_RINGS):
        size = rng.integers(RING_SIZE_RANGE[0], RING_SIZE_RANGE[1] + 1)
        members = available[idx: idx + size]
        idx += size
        ring_id = f"RING{ring_num:03d}"
        shared_device = f"DEV_RING_{ring_num:03d}"
        accounts.loc[accounts["account_id"].isin(members), ["is_fraud_ring_member", "ring_id"]] = [True, ring_id]
        ring_devices[ring_id] = {"members": members, "device": shared_device}
    return accounts, ring_devices


def generate_transactions(seed: int = RNG_SEED) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    accounts = _generate_accounts(rng)
    accounts, ring_devices = _assign_fraud_rings(accounts, rng)

    date_range = pd.date_range("2025-01-01", periods=N_MONTHS * 30, freq="D")
    rows = []
    txn_counter = 0

    normal_accounts = accounts[~accounts["is_fraud_ring_member"]]["account_id"].tolist()
    for account_id in normal_accounts:
        n_txns = rng.poisson(30)
        for _ in range(n_txns):
            txn_counter += 1
            day = rng.choice(date_range)
            amount = round(float(np.clip(rng.lognormal(mean=3.2, sigma=1.0), 1, 5000)), 2)
            is_organic_fraud = rng.random() < 0.004  # ~0.4% ordinary (non-ring) fraud
            if is_organic_fraud:
                amount = round(amount * rng.uniform(4, 10), 2)
            rows.append((
                f"T{txn_counter:08d}", account_id, day, amount, rng.choice(MERCHANT_CATEGORIES),
                f"DEV{rng.integers(0, N_ACCOUNTS * 2):06d}", f"IP{rng.integers(0, N_ACCOUNTS * 2):06d}",
                is_organic_fraud,
            ))

    for ring_id, info in ring_devices.items():
        burst_start = rng.choice(date_range[30:-10])
        burst_days = pd.date_range(burst_start, periods=rng.integers(2, 6), freq="D")
        for account_id in info["members"]:
            n_normal = rng.poisson(15)
            for _ in range(n_normal):
                txn_counter += 1
                day = rng.choice(date_range)
                amount = round(float(np.clip(rng.lognormal(mean=3.0, sigma=0.9), 1, 3000)), 2)
                rows.append((
                    f"T{txn_counter:08d}", account_id, day, amount, rng.choice(MERCHANT_CATEGORIES),
                    f"DEV{rng.integers(0, N_ACCOUNTS * 2):06d}", f"IP{rng.integers(0, N_ACCOUNTS * 2):06d}", False,
                ))
            n_fraud_burst = rng.integers(3, 10)
            shared_ip = f"IP_RING_{ring_id}"
            for _ in range(n_fraud_burst):
                txn_counter += 1
                day = rng.choice(burst_days)
                amount = round(float(np.clip(rng.lognormal(mean=5.5, sigma=0.6), 200, 8000)), 2)
                rows.append((
                    f"T{txn_counter:08d}", account_id, day, amount, rng.choice(MERCHANT_CATEGORIES),
                    info["device"], shared_ip, True,
                ))

    transactions = pd.DataFrame(rows, columns=[
        "transaction_id", "account_id", "txn_timestamp", "amount", "merchant_category",
        "device_id", "ip_address", "is_fraud",
    ])
    transactions["is_synthetic"] = True
    accounts["is_synthetic"] = True
    return accounts, transactions


def validate_transactions(df: pd.DataFrame):
    return validate_dataframe(
        df,
        required_columns=["transaction_id", "account_id", "txn_timestamp", "amount", "device_id", "ip_address"],
        not_null_columns=["transaction_id", "account_id", "device_id", "ip_address"],
        numeric_ranges={"amount": (0.01, 100_000)},
    )


def load_accounts(accounts: pd.DataFrame) -> int:
    return upsert_dataframe(accounts, schema="fraud_pattern", table="accounts", key_columns=["account_id"])


def load_transactions(transactions: pd.DataFrame) -> int:
    return bulk_upsert_dataframe(transactions, schema="fraud_pattern", table="transactions", key_columns=["transaction_id"])


def compute_graph_metrics(transactions: pd.DataFrame) -> pd.DataFrame:
    """Connect accounts that share a device or IP; flag accounts in
    abnormally large/dense connected components as ring-member candidates
    -- this is the graph-analytics / connected-account-analysis piece."""
    g = nx.Graph()
    g.add_nodes_from(transactions["account_id"].unique())

    for _, grp in transactions.groupby("device_id")["account_id"].unique().items():
        accts = list(grp)
        for i in range(len(accts)):
            for j in range(i + 1, len(accts)):
                g.add_edge(accts[i], accts[j], reason="shared_device")
    for _, grp in transactions.groupby("ip_address")["account_id"].unique().items():
        accts = list(grp)
        for i in range(len(accts)):
            for j in range(i + 1, len(accts)):
                g.add_edge(accts[i], accts[j], reason="shared_ip")

    components = {node: i for i, comp in enumerate(nx.connected_components(g)) for node in comp}
    component_sizes = pd.Series(components).value_counts()
    degree = dict(g.degree())

    rows = []
    for account_id in transactions["account_id"].unique():
        comp_id = components.get(account_id, -1)
        rows.append({
            "account_id": account_id,
            "component_id": int(comp_id),
            "component_size": int(component_sizes.get(comp_id, 1)),
            "degree": int(degree.get(account_id, 0)),
        })
    metrics = pd.DataFrame(rows)
    metrics["is_ring_candidate"] = metrics["component_size"] >= 3
    return metrics


def detect_anomalies(transactions: pd.DataFrame) -> pd.DataFrame:
    """IsolationForest over per-transaction behavioral features, scored
    per account against that account's own history (z-score-normalized
    amount) plus raw amount/hour -- an unsupervised anomaly score that
    doesn't see the `is_fraud` label, so evaluating it against that label
    afterward is a fair test, not circular."""
    from sklearn.ensemble import IsolationForest

    df = transactions.copy()
    df["txn_timestamp"] = pd.to_datetime(df["txn_timestamp"])
    df["hour"] = df["txn_timestamp"].dt.hour
    acct_stats = df.groupby("account_id")["amount"].agg(["mean", "std"]).rename(columns={"mean": "acct_mean", "std": "acct_std"})
    df = df.merge(acct_stats, on="account_id", how="left")
    df["acct_std"] = df["acct_std"].fillna(1).replace(0, 1)
    df["amount_zscore"] = (df["amount"] - df["acct_mean"]) / df["acct_std"]

    features = df[["amount", "amount_zscore", "hour"]].fillna(0)
    model = IsolationForest(n_estimators=200, contamination=0.05, random_state=RNG_SEED)
    df["anomaly_score"] = -model.fit_predict(features)  # 1 = anomalous, -1 -> flipped to 1
    df["anomaly_score"] = (df["anomaly_score"] + 1) / 2  # normalize to {0, 1}-ish
    df["raw_anomaly_score"] = -model.score_samples(features)  # continuous, higher = more anomalous

    return df[["transaction_id", "raw_anomaly_score", "anomaly_score"]].rename(
        columns={"anomaly_score": "is_flagged"}
    )


def load_graph_metrics(metrics: pd.DataFrame) -> int:
    return bulk_upsert_dataframe(metrics, schema="fraud_pattern", table="graph_metrics", key_columns=["account_id"])


def load_anomaly_scores(scores: pd.DataFrame) -> int:
    scores = scores.copy()
    scores["model_name"] = "isolation_forest_v1"
    return bulk_upsert_dataframe(
        scores, schema="fraud_pattern", table="anomaly_scores", key_columns=["transaction_id", "model_name"]
    )


def evaluate_model_and_load() -> dict:
    from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score

    from shared.database import get_engine

    engine = get_engine()
    df = pd.read_sql(
        "SELECT t.transaction_id, t.is_fraud, a.raw_anomaly_score, a.is_flagged "
        "FROM fraud_pattern.transactions t JOIN fraud_pattern.anomaly_scores a "
        "ON a.transaction_id = t.transaction_id",
        engine,
    )
    y_true = df["is_fraud"].astype(int)
    y_pred = (df["is_flagged"] > 0.5).astype(int)

    metrics = {
        "model_name": "isolation_forest_v1",
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true, df["raw_anomaly_score"])),
        "threshold": 0.5,
        # upsert_dataframe only refreshes columns present in this dict on a
        # rerun's ON CONFLICT UPDATE -- without this, computed_at would stay
        # frozen at whatever the very first INSERT's DEFAULT now() set,
        # silently misrepresenting every later rerun as the original run.
        "computed_at": datetime.now(timezone.utc),
    }
    upsert_dataframe(pd.DataFrame([metrics]), schema="fraud_pattern", table="model_evaluation", key_columns=["model_name"])
    return metrics


def generate_explainable_alerts() -> int:
    """Simple rule-based, human-readable alerts (not a black-box score) --
    combines the graph signal and the anomaly score so each alert says
    *why* a transaction was flagged."""
    from shared.database import get_engine, run_sql_file

    sql_path = os.path.join(os.path.dirname(__file__), "sql", "004_alerts.sql")
    run_sql_file(sql_path)
    engine = get_engine()
    with engine.connect() as conn:
        return int(conn.exec_driver_sql("SELECT COUNT(*) FROM fraud_pattern.alerts").scalar())


def compute_and_load_trends() -> int:
    from shared.database import get_engine, run_sql_file

    sql_path = os.path.join(os.path.dirname(__file__), "sql", "003_fraud_trends.sql")
    run_sql_file(sql_path)
    engine = get_engine()
    with engine.connect() as conn:
        return int(conn.exec_driver_sql("SELECT COUNT(*) FROM fraud_pattern.fraud_trends").scalar())
