# Project 4 — Fraud Pattern Evolution Tracker: Methodology & Limitations

## Data: 100% synthetic, with real evaluatable ground truth

No real transaction data is used. Real labeled fraud datasets are either gated behind a Kaggle
account/competition rules or under NDA in practice (see `docs/data_sources.md`), so
`pipeline.py` generates 5,000 synthetic accounts and ~150k+ transactions across 12 months.

The key design choice: **15 fraud rings** (3–8 accounts each) are injected, sharing a device/IP and
transacting in short bursts of unusually large amounts, plus a background ~0.4% "organic" (non-ring)
fraud rate on ordinary accounts. Because the generator *is* the ground truth
(`accounts.is_fraud_ring_member`, `transactions.is_fraud`), I can check the model-evaluation
metrics computed downstream (precision/recall/F1/ROC-AUC) against a real known answer, instead of
just reporting a score with nothing to verify it against.

## Graph / connected-account analysis (`fraud_pattern.graph_metrics`)

Accounts are connected in a graph whenever they share a `device_id` or `ip_address` (any real
transaction dimension could substitute here). Connected components are computed with `networkx`;
any account in a component of size ≥3 is flagged `is_ring_candidate`. This is the real detection
mechanism for the injected rings — no ground truth is used to build the graph, only to evaluate it.

## Anomaly detection (`fraud_pattern.anomaly_scores`)

An `IsolationForest` (unsupervised, `contamination=0.05`) scores each transaction on: raw amount,
the amount's z-score against that account's own history, and hour-of-day. **The model never sees
`is_fraud`** — it's trained purely on these features, so evaluating its output against the label
afterward is a fair test, not circular.

## Model evaluation (`fraud_pattern.model_evaluation`)

Precision/recall/F1 (at the 0.5 flagged threshold) and ROC-AUC of the isolation forest's raw
anomaly score, against the synthetic `is_fraud` label. The DAG's final data-quality task fails the
run if ROC-AUC drops to ≤0.5 (no better than random), catching a broken detector rather than
silently shipping one.

## Explainable alerts (`fraud_pattern.alerts`)

Deliberately rule-based, not a second black-box score: a transaction gets an alert row (with a
plain-English `reason`) when the anomaly model flags it, and a second, higher-severity alert when
it's *also* linked to a ≥3-account shared-device/IP cluster. Two independent signals agreeing is
the strongest evidence this project produces.

## Observed results (this build, 2026-09-12)

149,648 synthetic transactions generated, 1,115 (0.75%) truly fraudulent. Against that ground
truth, the isolation forest (at its default 0.5-flag threshold) scored: **ROC-AUC 0.93**, recall
0.78, precision 0.12, F1 0.20. The high ROC-AUC shows the model separates fraud from non-fraud
well; the low precision at this threshold is expected, not a bug — `contamination=0.05` flags
~5% of all transactions as anomalous while true fraud is ~0.75% of transactions, so roughly 1 in
9 flagged transactions is actually fraudulent. That precision/recall trade-off (catch most fraud,
accept many false positives for human review) is a realistic choice for a fraud *alerting* system,
not a final-decision one — a real deployment would tune `contamination` against a labeled
validation set and the business's actual review capacity, which this demo doesn't have.

## What this project does *not* do

- Does not use or approximate any real financial institution's transaction data.
- Does not claim the isolation-forest features (amount, z-score, hour) would generalize to real
  fraud patterns, which are far more varied — this demonstrates the *methodology* (unsupervised
  detection + graph analytics + ground-truth evaluation), not a production-ready model.
- Ring detection depends entirely on shared `device_id`/`ip_address` — a real fraud ring that
  never reuses infrastructure would not be caught by the graph signal here.
