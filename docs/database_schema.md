# Database Schema

Postgres 16, database `analytics`, schema `fraud_pattern`. Read-only role `analytics_ro` has
`SELECT` on everything here.

| Table | Grain | Notes |
|---|---|---|
| `accounts` | 1 row/synthetic account (5k) | fully synthetic; `is_fraud_ring_member`/`ring_id` are ground truth |
| `transactions` | 1 row/synthetic transaction (~150k+) | fully synthetic; `is_fraud` is ground truth |
| `graph_metrics` | 1 row/account | from NetworkX connected-components over shared device/IP |
| `anomaly_scores` | 1 row/transaction/model | IsolationForest output, never sees the fraud label |
| `model_evaluation` | 1 row/model | precision/recall/F1/ROC-AUC against ground truth |
| `fraud_trends` | 1 row/month | SQL-computed |
| `alerts` | 1 row/transaction/reason | rule-based, explainable |
| `powerbi_risk_summary`, `powerbi_trends`, `powerbi_network_summary` | views | pure passthrough/aggregation views for Power BI |

Every fact table has a natural-key primary key, so reruns upsert idempotently rather than
duplicate.
