-- Power BI-facing views for Project 4. Passthrough/aggregation views over
-- tables already populated by the pipeline's SQL steps -- no logic
-- duplicated here.

CREATE OR REPLACE VIEW fraud_pattern.powerbi_risk_summary AS
SELECT
    (SELECT COUNT(*) FROM fraud_pattern.transactions) AS total_transactions,
    (SELECT COUNT(DISTINCT transaction_id) FROM fraud_pattern.alerts) AS flagged_transactions,
    (SELECT COUNT(*) FROM fraud_pattern.transactions WHERE is_fraud) AS true_fraud_transactions,
    (SELECT SUM(amount) FROM fraud_pattern.transactions WHERE is_fraud) AS true_fraud_amount,
    (SELECT ROUND(AVG(CASE WHEN is_fraud THEN 1.0 ELSE 0.0 END)::numeric, 4) FROM fraud_pattern.transactions) AS true_fraud_rate,
    m.model_name, m.precision, m.recall, m.f1, m.roc_auc, m.threshold
FROM fraud_pattern.model_evaluation m;

CREATE OR REPLACE VIEW fraud_pattern.powerbi_trends AS
SELECT * FROM fraud_pattern.fraud_trends;

CREATE OR REPLACE VIEW fraud_pattern.powerbi_network_summary AS
SELECT
    g.account_id, a.account_type, a.home_country, a.is_fraud_ring_member, a.ring_id,
    g.component_id, g.component_size, g.degree, g.is_ring_candidate
FROM fraud_pattern.graph_metrics g
JOIN fraud_pattern.accounts a ON a.account_id = g.account_id;
