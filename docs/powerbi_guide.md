# Power BI Guide

## Status — read this first

A real `.pbip` project exists at `powerbi/FraudPatternEvolution.pbip`. Real and complete: 3
tables, all 9 DAX measures below (0 relationships — deliberate, see below), **16 real visual
objects across 2 pages** (12 data visuals + a header/footer text box per page — see
[Visual inventory](#visual-inventory)), a custom theme (`FraudPatternTheme.json`, wired into
`report.json`), and accent colors on the risk-indicator visuals (see Design system). The ideal
content for a confusion matrix still needs a new SQL view (no `powerbi_*` view currently exposes
true/false positive/negative counts, only aggregate metrics) — not yet added; the Detection
Performance cards use the real aggregate metrics instead, do not approximate a confusion matrix
from precision/recall in DAX.

**Power BI Desktop validation status: FULLY VERIFIED. Both pages confirmed rendering correctly
with real data, real colors, in Power BI Desktop** (see `docs/evidence/page1_executive_overview.png`
and `page2_fraud_trends_pattern_analysis.png`).

The root causes behind the original round-2 bugs (blank charts, no titles, a literal `\$`, wrong
date format, maps disabled for the tenant) were found on the sibling Climate Risk project and
fixed identically here — see Climate's `docs/powerbi_guide.md` for that diagnostic account. This
project's own file was then independently reopened in Desktop, where it first failed to load
entirely with "Your report has issues that could not be resolved" — `report.json`'s
`themeCollection.baseTheme.reportVersionAtImport` was a bare string (`"5.55"`) instead of the
required `{visual, report, page}` object. Fixed to match Climate's shape.

After that fix, the file loaded but with an empty local data cache — Import-mode `.pbip` files
carry no data of their own, so a first open needs an explicit Refresh (Home → Refresh) to pull rows
from Postgres; this is expected, not a bug, and all 3 tables (1 / 12 / 5,000 rows) loaded correctly
once refreshed. Separately, every chart Y-field bound as a raw, unaggregated `Column` reference
rendered as a completely empty plot area regardless of refresh state — fixed by pointing
`Avg Cluster Size by Home Country` at the existing `Avg Cluster Size` measure, and wrapping
`Transaction Volume vs. Fraud Volume` (`Function: 0`, Sum) and `Fraud Rate Over Time`
(`Function: 1`, Average) in Desktop's own confirmed `Aggregation` field shape, since no matching
measures existed for those `Trends` columns.

**Round 5 (this one) consolidated 4 pages down to 2**, on top of the same layout/background fixes
made across all 4 projects (see below). The original 4 pages ran 48–69% full by visual area — the
sparsest in the whole portfolio — and two of them duplicated content outright: "Executive
Overview"'s `Model Evaluation Summary` table and "Detection Performance"'s
`Detection Performance Detail` table had byte-for-byte identical field bindings (both querying the
same 6 columns off the single-row `RiskSummary` table), and both pages showed a `Model ROC AUC`
card. Those two pages merged into one — **"Executive Overview & Detection Performance"** — keeping
7 unique cards (deduplicating the repeated ROC AUC card) and one copy of the table, now at 85%
canvas fill. Separately, "Fraud Trends" (2 time-series charts, 69% full) and "Pattern & Network
Analysis" (a chart + a table, 49% full) merged into **"Fraud Trends & Pattern Analysis"** as a 2×2
grid — a natural trend-plus-pattern pairing that also matches the report's own name — now at 87%
fill. Both merges kept every visual's original field bindings and query state untouched; only
position, page assignment, and (for the two merged headers) the header text changed. Confirmed
via re-render that nothing broke: both pages reopened cleanly and every visual still shows its
correct data.

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

**Background**: a pale navy-tinted canvas `#DCE2EF` behind white visual containers. Set via
`FraudPatternTheme.json`'s `visualStyles.page.*.background` — **not** `outspace`, which doesn't
control the canvas (see Status above for how that was confirmed).

**Per-visual accent colors**: charts use `dataPoint.defaultColor` (single-measure charts only);
cards use `objects.labels[0].properties.color` (see Status above for why `dataPoint` doesn't work
on cards). Fraud Rate Over Time → critical red. Avg Cluster Size by Home Country → warning amber
(suspicious-activity indicator). Flagged Transactions card → warning amber; True Fraud Rate and
True Fraud Transactions cards → critical red. Transaction Volume vs. Fraud Volume (2 series) is
left theme-driven, per Microsoft's own caution against flattening a multi-series chart to one
color.

**Header/footer**: every page gets a themed header and footer as real `textbox` visuals,
including a synthetic-data disclosure in the header badge.

**Layout**: a standard dense grid — 16px canvas margin, 14px gutter between visuals, visuals
resized to fill their row/column exactly. Combined with the page consolidation above, both pages
now run 85–87% full by visual area, up from a 48–69% range across the original 4 sparser pages.

## Visual inventory

Every visual below is a real object in `powerbi/FraudPatternEvolution.Report/definition/pages/*/visuals/`.

**Page 1 — Executive Overview & Detection Performance**
- Total Transactions — Card — `RiskSummary[Total Transactions]`
- Flagged Transactions — Card — `RiskSummary[Flagged Transactions]`
- True Fraud Rate — Card — `RiskSummary[True Fraud Rate]`
- Model ROC AUC — Card — `RiskSummary[Model ROC AUC]`
- Model Precision — Card — `RiskSummary[Model Precision]`
- Model Recall — Card — `RiskSummary[Model Recall]`
- True Fraud Transactions — Card — `RiskSummary[True Fraud Transactions]`
- Model Evaluation Summary — Table — `RiskSummary[model_name]`, `[precision]`, `[recall]`, `[f1]`, `[roc_auc]`, `[threshold]` (the one copy that survived deduplication — see Status above)

**Page 2 — Fraud Trends & Pattern Analysis**
- Fraud Rate Over Time — Line chart — Category `Trends[month]`, Y `Trends[fraud_rate]` (Average aggregation)
- Transaction Volume vs. Fraud Volume — Clustered column chart — Category `Trends[month]`, Y `Trends[total_amount]`, `Trends[fraud_amount]` (Sum aggregation)
- Avg Cluster Size by Home Country — Clustered column chart — Category `NetworkSummary[home_country]`, Y `NetworkSummary[Avg Cluster Size]`
- Ring-Candidate Accounts — Table — account id/type/country, cluster id/size/degree, ring-candidate and ground-truth flags — deliberately a table, not a fabricated network diagram (no reliable first-party force-directed graph visual exists)

**Total: 16 visuals across 2 pages** (12 data visuals + a header and footer text box per page).

State on every page that all transaction/account data is synthetic.

## Power BI Service publication: BLOCKED

Needs a Power BI account/workspace and an On-premises Data Gateway — neither exists here.
