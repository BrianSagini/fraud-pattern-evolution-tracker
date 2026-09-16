# Fraud Pattern Evolution Tracker

I built this to answer a question most fraud-detection demos can't: does the anomaly score
actually catch fraud, or does it just look plausible? The transactions here are synthetic —
5,000 accounts, ~150,000 transactions, 15 fraud rings I injected as shared-device/IP clusters,
plus a background rate of organic fraud — but because I control the ground truth, I can score
the model against it honestly instead of eyeballing a chart.

Detection runs two independent signals: an IsolationForest anomaly model that never sees the
fraud label, and a graph pass (NetworkX connected components over shared device/IP) that surfaces
account clusters acting in coordination. Both get evaluated against the known-fraud labels, not
just reported as a black box.

**Stack**: Apache Airflow 3.3.1 → PostgreSQL 16 → Python (scikit-learn, NetworkX) / SQL →
Streamlit + Plotly → Power BI. Self-contained — this repo doesn't depend on its siblings (see
[Related projects](#related-projects)).

## Running it

```bash
cp .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # -> AIRFLOW_FERNET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"                                 # -> AIRFLOW_JWT_SECRET
# paste both into .env

docker compose up -d --build
docker compose ps
```

Then, from the Airflow UI (http://localhost:8081) or the CLI:

```bash
docker compose exec airflow-scheduler airflow dags unpause fraud_pattern_pipeline
docker compose exec airflow-scheduler airflow dags trigger fraud_pattern_pipeline
```

The DAG takes 15-20 minutes end to end (generation → graph analytics → model training →
evaluation). Dashboard's at http://localhost:8504 once it's done. `docker compose down` shuts
everything down without losing data.

## What the pipeline does

Ensure schema → generate the synthetic accounts and transactions → validate and load → graph
analytics and anomaly detection in parallel → evaluate the model against ground truth → generate
rule-based alerts I can actually explain (not just a score) → roll up monthly fraud trends →
publish the Power BI views → a data-quality gate that fails the run outright if ROC-AUC drops to
0.5 or below, since that would mean the model is doing no better than a coin flip.

## How well it actually works

Last run: ROC-AUC 0.93, recall 0.78, precision 0.12, against 1,115 true-fraud transactions.

That precision number looks bad until you know why it's there: the anomaly threshold
(`contamination=0.05`) flags roughly 5% of transactions, against a true fraud rate around 0.75%,
so it over-flags by design — about 1 in 9 flagged transactions is actually fraud. That's a real,
known tradeoff of unsupervised anomaly detection at this threshold (catch most fraud, accept a lot
of false positives for human review), not a bug I haven't gotten to, and it's not far off how
actual fraud-alert queues tend to run. A real deployment would tune `contamination` against a
labeled validation set and whatever review capacity the fraud team actually has — this project
demonstrates the detection methodology, not a tuned production threshold. Full walkthrough:
`docs/methodology.md`.

## Power BI

The report has 2 pages and 16 real visual objects, built from a data model I modeled by hand — 3
tables, 9 DAX measures, matched field-for-field against the SQL above. I originally split this
across 4 pages, but two of them turned out to duplicate a table and a KPI card outright once I
looked closely, so I merged them: page one now carries every KPI card plus the model evaluation
table, page two pairs the fraud-rate trend with the network-pattern breakdown, which reads better
together than apart.

Page two's ring-candidate table is a table on purpose, not a network diagram — Power BI doesn't
have a reliable first-party force-directed graph visual, and the table already answers what the
underlying data can support.

I opened every page in Power BI Desktop myself and confirmed each one renders with real data and
the right colors before calling this done — screenshots are in `docs/evidence/`. Full page layout,
DAX, and the color system are in `docs/powerbi_guide.md`.

## Docs

`docs/methodology.md` covers fraud-ring generation and the threshold tradeoff in more depth;
`docs/powerbi_guide.md` has the report build notes; `docs/database_schema.md` and
`docs/data_sources.md` cover the data model and sourcing.

## Related projects

Same portfolio, same pattern (Airflow → Postgres → dashboard → Power BI), different domain each
time: Climate Risk & Business Impact, Dark Store Intelligence, AI Hiring Bias Detector.
