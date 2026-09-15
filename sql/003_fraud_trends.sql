-- Monthly fraud trend (ground-truth is_fraud, not model predictions --
-- this table answers "how did fraud actually evolve," the model's own
-- precision/recall against this ground truth is in model_evaluation).
INSERT INTO fraud_pattern.fraud_trends (month, total_transactions, fraud_transactions, fraud_rate, total_amount, fraud_amount)
SELECT
    date_trunc('month', txn_timestamp)::date AS month,
    COUNT(*) AS total_transactions,
    COUNT(*) FILTER (WHERE is_fraud) AS fraud_transactions,
    ROUND((COUNT(*) FILTER (WHERE is_fraud))::numeric / NULLIF(COUNT(*), 0), 4) AS fraud_rate,
    SUM(amount) AS total_amount,
    SUM(amount) FILTER (WHERE is_fraud) AS fraud_amount
FROM fraud_pattern.transactions
GROUP BY date_trunc('month', txn_timestamp)
ON CONFLICT (month) DO UPDATE SET
    total_transactions = EXCLUDED.total_transactions,
    fraud_transactions = EXCLUDED.fraud_transactions,
    fraud_rate = EXCLUDED.fraud_rate,
    total_amount = EXCLUDED.total_amount,
    fraud_amount = EXCLUDED.fraud_amount;
