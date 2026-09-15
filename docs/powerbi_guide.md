# Power BI Guide

## Status — read this first

A real `.pbip` project exists at `powerbi/FraudPatternEvolution.pbip`, generated programmatically
— **never opened in Power BI Desktop, so not validated.** Real and complete: 3 tables, all 9 DAX
measures below (0 relationships — deliberate, see below). Placeholder: 4 report pages exist, named
correctly, zero visuals. Page 3's confusion-matrix breakdown additionally needs a new SQL view
(no `powerbi_*` view currently exposes true/false positive/negative counts, only aggregate
metrics) — not yet added; do not approximate one from precision/recall in DAX.

## Data connectivity

Get Data → Database → PostgreSQL database → `localhost:5433` / `analytics` / `analytics_ro`
(password from your `.env`). Mode: **Import**.

## Tables, relationships, measures

Tables: `fraud_pattern.powerbi_risk_summary` (single-row model+volume snapshot), `powerbi_trends`
(1 row/month), `powerbi_network_summary` (1 row/account).

**No relationships** — `powerbi_risk_summary` has no key to relate on; the other two are
independently sliceable.

```dax
Total Transactions = SUM(powerbi_risk_summary[total_transactions])
Flagged Transactions = SUM(powerbi_risk_summary[flagged_transactions])
True Fraud Transactions = SUM(powerbi_risk_summary[true_fraud_transactions])
True Fraud Rate = AVERAGE(powerbi_risk_summary[true_fraud_rate])
Model Precision = AVERAGE(powerbi_risk_summary[precision])
Model Recall = AVERAGE(powerbi_risk_summary[recall])
Model ROC AUC = AVERAGE(powerbi_risk_summary[roc_auc])
Ring Candidate Accounts = CALCULATE(DISTINCTCOUNT(powerbi_network_summary[account_id]), powerbi_network_summary[is_ring_candidate] = TRUE)
Avg Cluster Size = AVERAGE(powerbi_network_summary[component_size])
```
Precision/Recall/ROC-AUC are single-model-run outputs already computed in Python/scikit-learn
against real ground truth — expose as cards, never recompute a classification metric in DAX.

## Design system

Base: near-white `#F7F8FA` background, Segoe UI. This project's accents: primary navy `#14213D`,
secondary teal `#2E8B99`, warning amber `#E8A33D` (suspicious), critical red `#C0392B`
(confirmed/high-risk), neutral gray `#94A3B8` (normal transactions).

## Pages

1. **Executive Overview** — cards: Total Transactions, Flagged Transactions, True Fraud
   Transactions, True Fraud Rate, Model ROC AUC; banner noting ground truth is known by
   construction so these metrics are real, not illustrative.
2. **Fraud Trends** — `fraud_rate`/`fraud_amount` over month; month-range slicer.
3. **Detection Performance** — *(needs the new view above for a confusion matrix)* Precision/
   Recall/ROC AUC as large cards, with a text box explaining why precision is low at this
   threshold (copy the exact explanation from `docs/methodology.md`'s "Observed results" section —
   don't soften it).
4. **Pattern & Network Analysis** — a **table** of ring-candidate accounts by `component_size`/
   `degree`, with `is_fraud_ring_member`/`ring_id` visible for direct ground-truth comparison —
   deliberately not a fabricated network diagram.

State on every page that all transaction/account data is synthetic.

## Power BI Service publication: BLOCKED

Needs a Power BI account/workspace and an On-premises Data Gateway — neither exists here.
