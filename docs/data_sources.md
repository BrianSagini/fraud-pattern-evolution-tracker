# Data Sources

## 100% synthetic, by deliberate choice

I don't use any real transaction data here. Real, labeled fraud datasets are either gated behind
restrictive competition/NDA terms (e.g. Kaggle's credit-card-fraud datasets) or not something I'd
redistribute in a public portfolio repo. Instead, `pipeline.py` generates 5,000 synthetic accounts
and ~150,000 synthetic transactions with 15 explicitly injected fraud rings (shared device/IP
clusters) plus organic fraud — see `docs/methodology.md` for the exact generation logic. Because
I generated this data rather than scraping or anonymizing something real, I know the ground truth
(`is_fraud`) with certainty, which is what lets me check the model-evaluation metrics against a
real answer instead of just reporting a score.

No API key is required anywhere in this pipeline.
