-- Explainable, rule-based alerts -- combines the unsupervised anomaly
-- score with the graph (connected-account) signal so each alert states
-- *why* a transaction was flagged, rather than a bare black-box score.

INSERT INTO fraud_pattern.alerts (transaction_id, account_id, reason, severity, created_at)
SELECT
    t.transaction_id,
    t.account_id,
    'Unusual transaction pattern flagged by anomaly model (isolation forest)' AS reason,
    'medium' AS severity,
    now()
FROM fraud_pattern.transactions t
JOIN fraud_pattern.anomaly_scores a ON a.transaction_id = t.transaction_id AND a.model_name = 'isolation_forest_v1'
WHERE a.is_flagged > 0.5
ON CONFLICT (transaction_id, reason) DO NOTHING;

INSERT INTO fraud_pattern.alerts (transaction_id, account_id, reason, severity, created_at)
SELECT
    t.transaction_id,
    t.account_id,
    'Account shares a device/IP with ' || (g.component_size - 1) || ' other account(s) in a connected cluster' AS reason,
    'high' AS severity,
    now()
FROM fraud_pattern.transactions t
JOIN fraud_pattern.graph_metrics g ON g.account_id = t.account_id
JOIN fraud_pattern.anomaly_scores a ON a.transaction_id = t.transaction_id AND a.model_name = 'isolation_forest_v1'
WHERE g.is_ring_candidate AND a.is_flagged > 0.5
ON CONFLICT (transaction_id, reason) DO NOTHING;
