-- Fraud Pattern Evolution Tracker -- schema. 100% SYNTHETIC data
-- (accounts.is_synthetic / transactions.is_synthetic always true) --
-- see docs/methodology_fraud_pattern.md. is_fraud / is_fraud_ring_member
-- are the synthetic GROUND TRUTH the detection models are evaluated against.

CREATE TABLE IF NOT EXISTS fraud_pattern.accounts (
    account_id             TEXT PRIMARY KEY,
    account_type           TEXT,
    opened_date            DATE,
    home_country           TEXT,
    is_fraud_ring_member   BOOLEAN NOT NULL DEFAULT FALSE,
    ring_id                TEXT,
    is_synthetic           BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS fraud_pattern.transactions (
    transaction_id     TEXT PRIMARY KEY,
    account_id         TEXT NOT NULL REFERENCES fraud_pattern.accounts(account_id),
    txn_timestamp      TIMESTAMP NOT NULL,
    amount             NUMERIC NOT NULL,
    merchant_category  TEXT,
    device_id          TEXT NOT NULL,
    ip_address         TEXT NOT NULL,
    is_fraud           BOOLEAN NOT NULL DEFAULT FALSE,
    is_synthetic       BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS fraud_pattern.graph_metrics (
    account_id         TEXT PRIMARY KEY REFERENCES fraud_pattern.accounts(account_id),
    component_id       INT,
    component_size     INT,
    degree             INT,
    is_ring_candidate  BOOLEAN
);

CREATE TABLE IF NOT EXISTS fraud_pattern.anomaly_scores (
    transaction_id      TEXT NOT NULL REFERENCES fraud_pattern.transactions(transaction_id),
    model_name          TEXT NOT NULL,
    raw_anomaly_score   DOUBLE PRECISION,
    is_flagged          DOUBLE PRECISION,
    PRIMARY KEY (transaction_id, model_name)
);

CREATE TABLE IF NOT EXISTS fraud_pattern.model_evaluation (
    model_name    TEXT PRIMARY KEY,
    precision     DOUBLE PRECISION,
    recall        DOUBLE PRECISION,
    f1            DOUBLE PRECISION,
    roc_auc       DOUBLE PRECISION,
    threshold     DOUBLE PRECISION,
    computed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fraud_pattern.fraud_trends (
    month                DATE PRIMARY KEY,
    total_transactions   INT,
    fraud_transactions   INT,
    fraud_rate           DOUBLE PRECISION,
    total_amount         NUMERIC,
    fraud_amount         NUMERIC
);

CREATE TABLE IF NOT EXISTS fraud_pattern.alerts (
    transaction_id  TEXT NOT NULL REFERENCES fraud_pattern.transactions(transaction_id),
    account_id      TEXT NOT NULL REFERENCES fraud_pattern.accounts(account_id),
    reason          TEXT NOT NULL,
    severity        TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (transaction_id, reason)
);

CREATE INDEX IF NOT EXISTS idx_transactions_account ON fraud_pattern.transactions(account_id);
CREATE INDEX IF NOT EXISTS idx_transactions_timestamp ON fraud_pattern.transactions(txn_timestamp);
