"""Fraud Pattern Evolution Tracker -- synthetic data + detection logic.

100% SYNTHETIC transaction data. Real labeled fraud datasets are either
gated behind a Kaggle competition account or under NDA in practice (see
docs/data_sources.md) -- a generator with injected fraud rings is used
instead. Because the generator controls the ground truth here
(`is_fraud`/`is_fraud_ring_member`), the model-evaluation metrics
(precision/recall/F1/ROC-AUC) computed downstream can be checked against
a real known answer, not just reported as a score.
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
EVIDENCE_DIR = os.path.join(os.path.dirname(__file__), "docs", "evidence")


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


# Last 3 of 12 months held out as the test set. A random split would let
# February's fraud patterns leak into a January test fold -- no fraud
# model deployed for real ever gets scored on transactions from before
# the ones it trained on, so this project doesn't evaluate itself that
# way either.
SUPERVISED_TEST_SPLIT_DATE = "2025-10-01"

# accounts.is_fraud_ring_member / ring_id are deliberately excluded --
# they're literally how the synthetic ground truth was constructed, so
# using them as a feature would be leaking the label itself, not
# learning a real predictive signal.
SUPERVISED_NUMERIC_FEATURES = ["amount", "amount_zscore", "hour", "day_of_week", "component_size", "degree", "is_ring_candidate"]
SUPERVISED_CATEGORICAL_FEATURES = ["merchant_category", "account_type", "home_country"]


def _load_supervised_training_frame() -> pd.DataFrame:
    from shared.database import get_engine

    engine = get_engine()
    df = pd.read_sql(
        """
        SELECT t.transaction_id, t.account_id, t.txn_timestamp, t.amount,
               t.merchant_category, t.is_fraud,
               a.account_type, a.home_country,
               g.component_size, g.degree, g.is_ring_candidate
        FROM fraud_pattern.transactions t
        JOIN fraud_pattern.accounts a ON a.account_id = t.account_id
        LEFT JOIN fraud_pattern.graph_metrics g ON g.account_id = t.account_id
        """,
        engine,
    )
    df["txn_timestamp"] = pd.to_datetime(df["txn_timestamp"])
    df["hour"] = df["txn_timestamp"].dt.hour
    df["day_of_week"] = df["txn_timestamp"].dt.dayofweek
    df["is_ring_candidate"] = df["is_ring_candidate"].fillna(False).astype(int)
    df["component_size"] = df["component_size"].fillna(1)
    df["degree"] = df["degree"].fillna(0)
    return df


def _add_account_zscore(train: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-account amount z-score, fit on the train split only -- fitting
    it on the full dataset (train+test) would leak test-period spending
    behavior into a feature used to score the test set."""
    acct_stats = train.groupby("account_id")["amount"].agg(["mean", "std"]).rename(
        columns={"mean": "acct_mean", "std": "acct_std"}
    )
    acct_stats["acct_std"] = acct_stats["acct_std"].fillna(1).replace(0, 1)
    global_mean = float(train["amount"].mean())
    global_std = float(train["amount"].std() or 1.0)

    def _apply(split: pd.DataFrame) -> pd.DataFrame:
        out = split.merge(acct_stats, on="account_id", how="left")
        out["acct_mean"] = out["acct_mean"].fillna(global_mean)
        out["acct_std"] = out["acct_std"].fillna(global_std)
        out["amount_zscore"] = (out["amount"] - out["acct_mean"]) / out["acct_std"]
        return out.drop(columns=["acct_mean", "acct_std"])

    return _apply(train), _apply(test)


def build_supervised_features(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, "OneHotEncoder"]:
    """Split df by SUPERVISED_TEST_SPLIT_DATE, engineer features on each
    side independently (see _add_account_zscore), and fit the categorical
    encoder on the train split only. Returns (train, test, fitted_encoder)
    -- callers build the final X matrix with encode_features()."""
    from sklearn.preprocessing import OneHotEncoder

    train = df[df["txn_timestamp"] < SUPERVISED_TEST_SPLIT_DATE].copy()
    test = df[df["txn_timestamp"] >= SUPERVISED_TEST_SPLIT_DATE].copy()
    train, test = _add_account_zscore(train, test)

    encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    encoder.fit(train[SUPERVISED_CATEGORICAL_FEATURES])
    return train, test, encoder


def encode_features(split: pd.DataFrame, encoder: "OneHotEncoder") -> tuple[np.ndarray, list[str]]:
    numeric = split[SUPERVISED_NUMERIC_FEATURES].fillna(0).to_numpy()
    cats = encoder.transform(split[SUPERVISED_CATEGORICAL_FEATURES])
    feature_names = SUPERVISED_NUMERIC_FEATURES + list(encoder.get_feature_names_out(SUPERVISED_CATEGORICAL_FEATURES))
    return np.hstack([numeric, cats]), feature_names


def build_supervised_models(scale_pos_weight: float) -> dict:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from xgboost import XGBClassifier

    return {
        "logistic_regression": LogisticRegression(
            max_iter=2000, class_weight="balanced", random_state=RNG_SEED
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=300, max_depth=10, class_weight="balanced", random_state=RNG_SEED, n_jobs=-1
        ),
        "xgboost": XGBClassifier(
            n_estimators=300, max_depth=5, learning_rate=0.1,
            scale_pos_weight=scale_pos_weight, eval_metric="logloss", random_state=RNG_SEED,
        ),
    }


def train_supervised_models() -> dict:
    """Train Logistic Regression, Random Forest, and XGBoost on the known
    `is_fraud` label with the time-based split above, and evaluate every
    one of them -- plus the existing unsupervised IsolationForest -- on
    the same held-out test set for a fair head-to-head. Writes every
    model's real metrics to fraud_pattern.model_evaluation (whichever way
    they land: a model that loses to IsolationForest here is left in the
    table as a real result, not filtered out), the test-set predictions
    to fraud_pattern.anomaly_scores, and each model's feature importances
    to fraud_pattern.feature_importance."""
    from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score

    df = _load_supervised_training_frame()
    train, test, encoder = build_supervised_features(df)
    X_train, feature_names = encode_features(train, encoder)
    X_test, _ = encode_features(test, encoder)
    y_train = train["is_fraud"].astype(int).to_numpy()
    y_test = test["is_fraud"].astype(int).to_numpy()

    scale_pos_weight = (y_train == 0).sum() / max(int((y_train == 1).sum()), 1)
    models = build_supervised_models(scale_pos_weight)

    all_metrics, all_predictions, importance_rows = [], [], []
    fitted, probas = {}, {}
    computed_at = datetime.now(timezone.utc)

    for model_name, model in models.items():
        model.fit(X_train, y_train)
        proba = model.predict_proba(X_test)[:, 1]
        pred = (proba >= 0.5).astype(int)
        fitted[model_name] = model
        probas[model_name] = proba

        all_metrics.append({
            "model_name": model_name,
            "precision": float(precision_score(y_test, pred, zero_division=0)),
            "recall": float(recall_score(y_test, pred, zero_division=0)),
            "f1": float(f1_score(y_test, pred, zero_division=0)),
            "roc_auc": float(roc_auc_score(y_test, proba)),
            "threshold": 0.5,
            "computed_at": computed_at,
        })
        all_predictions.append(pd.DataFrame({
            "transaction_id": test["transaction_id"].to_numpy(),
            "model_name": model_name,
            "raw_anomaly_score": proba,
            "is_flagged": pred.astype(float),
        }))

        if hasattr(model, "feature_importances_"):
            importances = model.feature_importances_
        else:
            importances = np.abs(model.coef_[0])
            importances = importances / importances.sum()
        for rank, idx in enumerate(np.argsort(-importances), start=1):
            importance_rows.append({
                "model_name": model_name,
                "feature_name": feature_names[idx],
                "importance": float(importances[idx]),
                "rank": rank,
                "computed_at": computed_at,
            })

    upsert_dataframe(pd.DataFrame(all_metrics), schema="fraud_pattern", table="model_evaluation", key_columns=["model_name"])
    bulk_upsert_dataframe(
        pd.concat(all_predictions, ignore_index=True), schema="fraud_pattern", table="anomaly_scores",
        key_columns=["transaction_id", "model_name"],
    )
    bulk_upsert_dataframe(
        pd.DataFrame(importance_rows), schema="fraud_pattern", table="feature_importance",
        key_columns=["model_name", "feature_name"],
    )

    iso_raw, iso_flagged = _load_isolation_forest_test_scores(test["transaction_id"])

    # The existing isolation_forest_v1 row in model_evaluation is computed
    # over the full year (see evaluate_model_and_load) -- not the same
    # population as the 3 supervised models above, which only ever see the
    # Oct-Dec test window. Comparing those numbers directly would be
    # comparing two different test sets, not a fair head-to-head. This
    # second row re-evaluates the *same* unsupervised model's *existing*
    # predictions restricted to that exact window, so the four models can
    # actually be compared apples-to-apples. The original full-year row is
    # left untouched -- other docs and the Power BI report reference it.
    iso_test_metrics = {
        "model_name": "isolation_forest_v1_test_window",
        "precision": float(precision_score(y_test, iso_flagged, zero_division=0)),
        "recall": float(recall_score(y_test, iso_flagged, zero_division=0)),
        "f1": float(f1_score(y_test, iso_flagged, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_test, iso_raw)),
        "threshold": 0.5,
        "computed_at": computed_at,
    }
    upsert_dataframe(pd.DataFrame([iso_test_metrics]), schema="fraud_pattern", table="model_evaluation", key_columns=["model_name"])
    all_metrics_with_baseline = all_metrics + [iso_test_metrics]

    supervised_preds = {name: (proba >= 0.5).astype(int) for name, proba in probas.items()}
    save_evaluation_artifacts(
        y_test=y_test,
        probas={"isolation_forest_v1": iso_raw, **probas},
        fitted_models=fitted,
        X_test=X_test,
        feature_names=feature_names,
        preds={"isolation_forest_v1": iso_flagged, **supervised_preds},
    )

    return {
        "metrics": all_metrics_with_baseline,
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "train_fraud": int(y_train.sum()),
        "test_fraud": int(y_test.sum()),
    }


def _load_isolation_forest_test_scores(test_transaction_ids: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Pull the existing unsupervised model's scores for the same test-set
    transaction ids, so the comparison plots/metrics use its real,
    already-computed predictions rather than retraining it a second time.
    Returns (raw_anomaly_score, is_flagged) -- the raw score is continuous
    (used for ROC-AUC, which only needs a ranking), is_flagged is the
    model's own {0,1} decision (used for precision/recall/F1, since a 0.5
    cut on the raw score isn't the threshold IsolationForest actually
    used)."""
    from shared.database import get_engine

    engine = get_engine()
    ids = pd.DataFrame({"transaction_id": test_transaction_ids})
    scores = pd.read_sql(
        "SELECT transaction_id, raw_anomaly_score, is_flagged FROM fraud_pattern.anomaly_scores "
        "WHERE model_name = 'isolation_forest_v1'",
        engine,
    )
    merged = ids.merge(scores, on="transaction_id", how="left")
    raw = merged["raw_anomaly_score"].fillna(0).to_numpy()
    flagged = (merged["is_flagged"].fillna(0) > 0.5).astype(int).to_numpy()
    return raw, flagged


def save_evaluation_artifacts(
    *,
    y_test: np.ndarray,
    probas: dict[str, np.ndarray],
    fitted_models: dict,
    X_test: np.ndarray,
    feature_names: list[str],
    preds: dict[str, np.ndarray] | None = None,
) -> None:
    """Confusion matrices + ROC curves for all 4 models (the 3 supervised
    ones plus the existing IsolationForest), and a SHAP summary plot for
    XGBoost -- saved as real PNGs from this actual run, not mocked.

    `probas` are continuous scores, used for ROC curves (only the ranking
    matters, so IsolationForest's differently-scaled raw_anomaly_score
    works fine here). `preds` are each model's actual binary decision,
    used for confusion matrices -- for the 3 supervised models that's a
    0.5 cut on a real probability, but IsolationForest's raw score isn't a
    0-1 probability, so its own `is_flagged` decision must be passed in
    explicitly rather than assumed from a 0.5 cut on `probas`."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import shap
    from sklearn.metrics import ConfusionMatrixDisplay, roc_auc_score, roc_curve

    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    model_order = ["isolation_forest_v1", "logistic_regression", "random_forest", "xgboost"]
    preds = preds or {}

    fig, axes = plt.subplots(1, 4, figsize=(20, 5))
    for ax, model_name in zip(axes, model_order):
        pred = preds.get(model_name, (probas[model_name] >= 0.5).astype(int))
        ConfusionMatrixDisplay.from_predictions(
            y_test, pred, ax=ax, colorbar=False, cmap="Blues", display_labels=["legit", "fraud"]
        )
        ax.set_title(model_name)
    fig.suptitle("Confusion matrices on the held-out test set (Oct-Dec 2025), threshold 0.5")
    fig.tight_layout()
    fig.savefig(os.path.join(EVIDENCE_DIR, "fraud_confusion_matrices.png"), dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 6))
    for model_name in model_order:
        fpr, tpr, _ = roc_curve(y_test, probas[model_name])
        auc = roc_auc_score(y_test, probas[model_name])
        ax.plot(fpr, tpr, label=f"{model_name} (AUC={auc:.3f})")
    ax.plot([0, 1], [0, 1], "k--", alpha=0.3, label="random")
    ax.set_xlabel("False positive rate")
    ax.set_ylabel("True positive rate")
    ax.set_title("ROC curves on the held-out test set")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(os.path.join(EVIDENCE_DIR, "fraud_roc_curves.png"), dpi=150)
    plt.close(fig)

    xgb_model = fitted_models["xgboost"]
    sample_size = min(2000, X_test.shape[0])
    rng = np.random.default_rng(RNG_SEED)
    sample_idx = rng.choice(X_test.shape[0], size=sample_size, replace=False)
    X_sample = X_test[sample_idx]
    explainer = shap.TreeExplainer(xgb_model)
    shap_values = explainer.shap_values(X_sample)

    shap.summary_plot(
        shap_values, X_sample, feature_names=feature_names, plot_type="bar", show=False, max_display=12
    )
    fig = plt.gcf()
    fig.set_size_inches(11, 6)
    plt.title(f"XGBoost mean |SHAP| feature importance\n({sample_size} test-set transactions)")
    fig.tight_layout()
    fig.savefig(os.path.join(EVIDENCE_DIR, "fraud_shap_importance.png"), dpi=150)
    plt.close(fig)


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
