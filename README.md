# 🕸️ Fraud Pattern Evolution Tracker

An end-to-end fraud analytics platform: 100% synthetic transactions with injected fraud rings and
known ground truth, detected with unsupervised anomaly detection and graph (shared-device/IP)
analysis. Part of a 4-project data analytics portfolio ([siblings](#related-projects) below); this
repo is fully self-contained and runs on its own.

**Stack**: Apache Airflow 3.3.1 → PostgreSQL 16 → Python (scikit-learn, NetworkX)/SQL →
Streamlit + Plotly → Power BI (`.pbip` project included, unvalidated — see [Power BI](#power-bi)).

## Data

**100% synthetic** — 5,000 accounts, ~150,000 transactions, 15 injected fraud rings (shared
device/IP clusters) plus ~0.4% organic fraud. Because the ground truth (`is_fraud`) is known by
construction, the model-evaluation metrics below are **genuinely meaningful**, unlike most fraud
demos that have nothing to check anomaly scores against. Full generation methodology:
`docs/methodology.md`.

## Quick start

```bash
cp .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # -> AIRFLOW_FERNET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"                                 # -> AIRFLOW_JWT_SECRET
# paste both into .env

docker compose up -d --build
docker compose ps
```

Airflow UI: http://localhost:8081.

```bash
docker compose exec airflow-scheduler airflow dags unpause fraud_pattern_pipeline
docker compose exec airflow-scheduler airflow dags trigger fraud_pattern_pipeline
```

Dashboard: http://localhost:8504 once the DAG completes (~15-20 minutes).

Shut down (keeps data): `docker compose down`.

## Pipeline

`fraud_pattern_pipeline` DAG: ensure schema → generate synthetic accounts/transactions → validate
& load → graph analytics (NetworkX connected components over shared device/IP) + anomaly
detection (IsolationForest, never sees the fraud label) → evaluate the model against real ground
truth → generate explainable rule-based alerts → compute monthly fraud trends (SQL) → build Power
BI views → data-quality check (fails if ROC-AUC ≤ 0.5, i.e. no better than random).

## What the numbers mean

Last real run: **ROC-AUC 0.93, recall 0.78, precision 0.12** against 1,115 true-fraud transactions.
Precision is low because the anomaly threshold (`contamination=0.05`) over-flags relative to the
true ~0.75% fraud rate — a documented threshold-tuning limitation of an unsupervised model, not a
bug; a real fraud-alert queue commonly runs at similar precision. Full detail:
`docs/methodology.md`.

## Power BI

A real `.pbip` project (`powerbi/FraudPatternEvolution.pbip`) exists with the complete data model
— 3 tables, 9 DAX measures — **and 14 real visuals across all 4 pages** (see
`docs/powerbi_guide.md`'s visual inventory; page 3's ideal confusion-matrix breakdown additionally
needs a new SQL view, so it uses the real aggregate metrics instead for now). **Rendering is not
verified**: the outer project structure was confirmed openable by Power BI Desktop in one safe
test on a sibling project, but the visual JSON itself was never opened (a second validation
attempt captured unrelated desktop content and was stopped — full account in
`docs/powerbi_guide.md`). Page 4 is a table of ring-candidate accounts, not a fabricated network
diagram — Power BI has no reliable first-party
force-directed graph visual, and the table already answers what the data supports.

## Documentation

`docs/methodology.md` · `docs/powerbi_guide.md` · `docs/database_schema.md` · `docs/data_sources.md`.

## Related projects

Part of a 4-project portfolio, each in its own self-contained repo: Climate Risk & Business
Impact, Dark Store Intelligence, AI Hiring Bias Detector.
