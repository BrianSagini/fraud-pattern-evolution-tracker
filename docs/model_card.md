# Model card — fraud detection

Four models detect fraud in this project, evaluated head-to-head on the same held-out data. This
card covers the three supervised ones added this round; the existing unsupervised IsolationForest
is included in every comparison table for context.

## Data

100% synthetic — see `docs/data_sources.md` and `docs/methodology.md` for how the fraud rings and
transactions are generated. 149,648 transactions across 12 months (Jan–Dec 2025), 1,115 (0.75%)
labeled fraud.

**Split**: time-based, not random. Train = Jan–Sep 2025 (113,307 rows, 827 fraud). Test = Oct–Dec
2025 (36,341 rows, 288 fraud), held out completely — no test-period transaction, account statistic,
or encoder category is used anywhere in training. A random split would let September's fraud
patterns leak into an August test fold; no fraud model deployed for real gets scored on
transactions from before the ones it trained on, so this project doesn't evaluate itself that way
either.

## Features

`amount`, `amount_zscore` (per-account, fit on the train split only), `hour`, `day_of_week`,
`component_size`/`degree`/`is_ring_candidate` (from the existing graph analysis),
`merchant_category`/`account_type`/`home_country` (one-hot encoded, fit on train only).

**Deliberately excluded**: `accounts.is_fraud_ring_member` and `ring_id`. Those columns are
literally how the synthetic ground truth was constructed — using them as a feature would be
leaking the label itself, not learning a real predictive signal.

**Two real limitations worth stating plainly, both found while building this**:

1. `component_size` and `degree` come from a graph built over the *entire* transaction history
   (device/IP connections across all 12 months, not just the train period), because that's how the
   existing graph-analysis table is materialized in Postgres. That means an early transaction's
   graph feature can be informed by device/IP links formed later in the year — a small amount of
   future information leaking into what's nominally a "train-only" feature. It's a real
   methodological gap, not something to paper over; a stricter version of this project would
   rebuild the graph as-of each split boundary.
2. `component_size` and `is_ring_candidate` turned out to be **constant across every single
   account** — all 5,000 accounts land in one giant connected component (`component_size = 5000`,
   `is_ring_candidate = true` for 100% of them), because device/IP ids are drawn from a shared pool
   across every normal transaction in the generator, and at this data volume that's enough
   incidental overlap to merge the whole account population into one component. A constant feature
   carries zero information to any model, which is exactly why neither shows up in the SHAP
   ranking below — `degree` (which does vary meaningfully account-to-account) is the only part of
   the existing graph analysis doing real work here. I found this by checking the raw distribution
   after noticing both features missing from the SHAP importance plot, not by assuming it — see
   `fraud_model_comparison.ipynb` for the query.

## Models and real, held-out results

Same test set, same threshold (0.5) for all four:

| Model | Precision | Recall | F1 | ROC-AUC |
|---|---|---|---|---|
| IsolationForest (unsupervised, re-scored on this test window) | 0.126 | 0.795 | **0.218** | 0.927 |
| Logistic Regression | 0.081 | 0.823 | 0.147 | **0.947** |
| Random Forest | 0.108 | 0.774 | 0.190 | 0.931 |
| XGBoost | 0.077 | 0.333 | 0.125 | 0.801 |

None of the three supervised models beats the unsupervised baseline on F1 or precision. Logistic
Regression does edge it out on ROC-AUC (0.947 vs 0.927) and has the highest recall of the four
(0.823) — the best model here depends entirely on what you're optimizing for, and there isn't one
model that wins on every axis.

**XGBoost is the honest surprise**: the most complex model tried is the worst performer on every
single metric, missing 2 out of every 3 fraud cases in the test set (96 caught of 288). With only
827 positive training examples, its 300 trees at depth 5 most plausibly overfit harder than Random
Forest's bagged, shallower ensemble or Logistic Regression's much simpler decision boundary — this
result came from running the same hyperparameters used for Random Forest's tree count without
separately tuning XGBoost for this specific class imbalance, and that's a fair thing to hold
against this run's setup, not a claim that gradient boosting can't work here. A tuned XGBoost
(learning-rate schedule, early stopping against a validation fold, a properly swept
`scale_pos_weight`) would likely close some of this gap; this project reports what the untuned run
actually did, not what a better-tuned one probably would.

Full confusion matrices, ROC curves, and the SHAP importance plot: `docs/evidence/`.

## What drives the predictions

SHAP on XGBoost (mean absolute impact, 2,000 test-set transactions): `amount` dominates by a wide
margin, followed by the two graph-analysis features (`degree`, `amount_zscore`) — the existing
network signal carries real predictive value for a supervised model too, not just for flagging
ring candidates directly. Categorical features (merchant category, account type, home country)
contribute comparatively little.

## Comparison against automated model search

As a sanity check on the hand-picked comparison above, `fraud_model_comparison.ipynb` also runs
H2O AutoML (community edition, local-only, not part of the Airflow pipeline) over the exact same
one-hot-encoded train/test matrices, 5-minute budget. Its leader — a `StackedEnsemble` combining
H2O's GLM/GBM/DRF models — reaches **ROC-AUC 0.9429** on this project's real held-out test set,
computed the same way as every other number in this card, not H2O's internal cross-validation
score. That's close to, but does not beat, the hand-picked **Logistic Regression's 0.947**, which
stays the best of the four original models. H2O's own XGBoost backend wasn't available on this
machine and was skipped automatically, so this search covers GLM/GBM/DRF/StackedEnsemble rather
than every algorithm family — a caveat on the sanity check, not on the result: an automated search
across what *was* available didn't find anything better than a model already in the comparison.

Independently of the win/loss result, H2O's own preprocessing flagged `component_size` and
`is_ring_candidate` as constant/dropped columns in every model it built — the same
giant-connected-component finding two sections up, reached by H2O's automated data checks rather
than the manual investigation that originally surfaced it.

**Seeing real predictions**: the notebook also exports the exact test frame every model above was
scored against to `h2o_saved_models/test_frame.csv` (target column included), and
`view_all_ml_in_h2o.py` (outside this repo, local-only) loads it into Flow as `fraud_test_frame`
alongside the saved models. In Flow: Models → pick a model (e.g. the leader named in the table
above) → Predict → select `fraud_test_frame` → Flow computes and displays a real predictions table
for that model against that data, comparable directly to the `is_fraud` column already in the
frame.

## Intended use

This is a methodology demonstration — time-based evaluation, a fair multi-model comparison, and
explainability on synthetic data with known ground truth — not a fraud model meant to be deployed
on anyone's real transactions. Precision at this threshold (7–13%) means most flagged transactions
in every model here are false positives; a real deployment would tune the threshold against actual
review capacity, exactly as `docs/methodology.md` already says about the original IsolationForest.

## Known limitations

- The graph-feature leakage described above.
- No hyperparameter search was run for any of the three supervised models — every result here is
  one reasonable, untuned configuration, not each model's best possible showing.
- One time-based split, not walk-forward cross-validation — a single Oct–Dec test window is a
  reasonable demonstration of the *method*, not a robust estimate of how stable these numbers
  would be across other quarters.
- SHAP is computed for XGBoost only, on a 2,000-row sample of the test set for runtime reasons, not
  the full 36,341.
