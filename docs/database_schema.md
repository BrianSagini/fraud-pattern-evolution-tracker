# Database Schema

Postgres 16, database `analytics`, schema `fraud_pattern`. Read-only role `analytics_ro` has
`SELECT` on everything here.

| Table | Grain | Notes |
|---|---|---|
| `accounts` | 1 row/synthetic account (5k) | fully synthetic; `is_fraud_ring_member`/`ring_id` are ground truth |
| `transactions` | 1 row/synthetic transaction (~150k+) | fully synthetic; `is_fraud` is ground truth |
| `graph_metrics` | 1 row/account | from NetworkX connected-components over shared device/IP |
| `anomaly_scores` | 1 row/transaction/model | `isolation_forest_v1` (unsupervised, full dataset) plus `logistic_regression`/`random_forest`/`xgboost` (supervised, test-set rows only -- see below) |
| `model_evaluation` | 1 row/model | precision/recall/F1/ROC-AUC against ground truth; includes `isolation_forest_v1_test_window`, the same unsupervised model re-scored on just the supervised models' held-out test period for a fair head-to-head (the original `isolation_forest_v1` row is evaluated over the full year and isn't a like-for-like comparison) |
| `feature_importance` | 1 row/model/feature | `random_forest`/`xgboost`'s built-in importances and `logistic_regression`'s normalized absolute coefficients |
| `fraud_trends` | 1 row/month | SQL-computed |
| `alerts` | 1 row/transaction/reason | rule-based, explainable |
| `powerbi_risk_summary`, `powerbi_trends`, `powerbi_network_summary` | views | pure passthrough/aggregation views for Power BI |

Every fact table has a natural-key primary key, so reruns upsert idempotently rather than
duplicate. The supervised models only ever write predictions for the Oct-Dec 2025 test window in
`anomaly_scores` -- they were never fit on it, so writing predictions for the training rows too
would mix genuinely-held-out scores with in-sample ones in the same table without a way to tell
them apart.
