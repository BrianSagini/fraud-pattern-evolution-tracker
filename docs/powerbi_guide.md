# Power BI Guide

## Status — read this first

A real `.pbip` project exists at `powerbi/FraudPatternEvolution.pbip`. Real and complete: 3
tables, all 9 DAX measures below (0 relationships — deliberate, see below), **22 real visual
objects across all 4 pages** (18 data visuals + a header/footer text box per page — see
[Visual inventory](#visual-inventory)), a custom theme (`FraudPatternTheme.json`, wired into
`report.json`), and accent colors on the risk-indicator visuals (see Design system). Page 3's
ideal content (a confusion matrix) still needs a new SQL view (no `powerbi_*` view currently
exposes true/false positive/negative counts, only aggregate metrics) — not yet added; page 3 uses
the real aggregate metrics instead, do not approximate a confusion matrix from precision/recall
in DAX.

**Power BI Desktop validation status: PARTIALLY VERIFIED, via the sibling Climate Risk project.**
The project owner actually opened `ClimateRisk.pbip` and reported real bugs (blank charts, no
titles, a literal `\$`, wrong date format, maps disabled for their tenant) — root causes found and
fixed identically across all 4 projects, this one included (full diagnostic account in Climate's
`docs/powerbi_guide.md`). **This project's own file has not been independently reopened** — its
fixes and this round's styling are structurally validated (every field/measure reference checked
against the live model, no overlaps, no blank pages) but not yet confirmed by an actual render.
If you open this file and something doesn't render correctly, that's real information — say so.

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

## Design system — now actually applied, not just documented

Segoe UI. Accents: primary navy `#14213D`, secondary teal `#2E8B99`, warning amber `#E8A33D`
(suspicious), critical red `#C0392B` (confirmed/high-risk), neutral gray `#94A3B8` (normal
transactions).

**Background**: a pale navy-tinted canvas `#ECEFF5` behind white visual containers — same
reasoning as Climate's (see that project's guide for the 3 options weighed).

**Per-visual accent colors** (`dataPoint.defaultColor`, single-measure charts only): Fraud Rate
Over Time → critical red. Avg Cluster Size by Home Country → warning amber (suspicious-activity
indicator). Flagged Transactions card → warning amber; True Fraud Rate and True Fraud
Transactions cards → critical red. Transaction Volume vs. Fraud Volume (2 series) is left
theme-driven, per Microsoft's own caution against flattening a multi-series chart to one color.

**Header/footer**: every page gets a themed header and footer as real `textbox` visuals,
including a synthetic-data disclosure in the header badge.

## Visual inventory

Every visual below is a real object in `powerbi/FraudPatternEvolution.Report/definition/pages/*/visuals/`.

**Page 1 — Executive Overview**
- Total Transactions — Card — `RiskSummary[Total Transactions]`
- Flagged Transactions — Card — `RiskSummary[Flagged Transactions]`
- True Fraud Rate — Card — `RiskSummary[True Fraud Rate]`
- Model ROC AUC — Card — `RiskSummary[Model ROC AUC]`
- Model Evaluation Summary — Table — `RiskSummary[model_name]`, `[precision]`, `[recall]`, `[f1]`, `[roc_auc]`, `[threshold]`

**Page 2 — Fraud Trends**
- Fraud Rate Over Time — Line chart — Category `Trends[month]`, Y `Trends[fraud_rate]`
- Transaction Volume vs. Fraud Volume — Clustered column chart — Category `Trends[month]`, Y `Trends[total_amount]`, `Trends[fraud_amount]`

**Page 3 — Detection Performance**
- Model Precision — Card — `RiskSummary[Model Precision]`
- Model Recall — Card — `RiskSummary[Model Recall]`
- Model ROC AUC — Card — `RiskSummary[Model ROC AUC]`
- True Fraud Transactions — Card — `RiskSummary[True Fraud Transactions]`
- Detection Performance Detail — Table — same 6 columns as page 1's summary table

**Page 4 — Pattern & Network Analysis**
- Avg Cluster Size by Home Country — Clustered column chart — Category `NetworkSummary[home_country]`, Y `NetworkSummary[component_size]`
- Ring-Candidate Accounts — Table — account id/type/country, cluster id/size/degree, ring-candidate and ground-truth flags — deliberately a table, not a fabricated network diagram (no reliable first-party force-directed graph visual exists)
- Ring-Candidate Accounts by Country — Map — Category `NetworkSummary[home_country]` (geocoded by name, no lat/lon field exists on this table), Size `NetworkSummary[Ring Candidate Accounts]`

**Total: 15 visuals across 4 pages.**

State on every page that all transaction/account data is synthetic.

## Power BI Service publication: BLOCKED

Needs a Power BI account/workspace and an On-premises Data Gateway — neither exists here.
