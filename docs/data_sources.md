# Data Sources

## 100% synthetic, by deliberate choice

No real transaction data is used anywhere in this project. Real, labeled fraud datasets are either
gated behind restrictive competition/NDA terms (e.g. Kaggle credit-card-fraud datasets) or
unsuitable to redistribute in a public portfolio repo. Instead, `pipeline.py` generates 5,000
synthetic accounts and ~150,000 synthetic transactions with 15 explicitly injected fraud rings
(shared device/IP clusters) plus organic fraud — see `docs/methodology.md` for the exact
generation logic. Because this is generated, not scraped or anonymized real data, the ground truth
(`is_fraud`) is known with certainty, which is what makes the model-evaluation metrics in this
project genuinely meaningful rather than illustrative.

No API key is required anywhere in this pipeline.
