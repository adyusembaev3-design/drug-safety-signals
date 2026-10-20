# Drug Safety Signal Detection from FDA Adverse Event Reports

Finds side effects that are reported unusually often with a drug, using the FDA Adverse Event Reporting System (FAERS), and checks the method against three JAK inhibitors (tofacitinib, upadacitinib, baricitinib) whose class safety warnings are well documented. A streaming extension monitors JAK inhibitor reports in real time with Kafka, Prometheus and Grafana.

**Live dashboard:** https://drug-safety-app.proudforest-f5b99821.northcentralus.azurecontainerapps.io (hosted on Azure Container Apps; it may take a few seconds to wake up)

> FAERS is voluntary, unverified reporting. A statistical signal is a lead for experts to investigate. It does not show that a drug causes a side effect.

## Overview

| | |
|---|---|
| **Data** | FAERS quarterly files, 2018 Q1 to 2026 Q2 (34 quarters) |
| **Scale** | About 14.6M demographic and 64M drug records, reduced to about 12M unique cases |
| **Methods** | PRR, ROR with 95% CI, chi-square, Evans rule, information component (IC025) |
| **Validation** | Three JAK inhibitors against active comparators, quarter-by-quarter replay, time to onset |
| **Real-time** | Kafka streaming of new reports, live PRR/chi-square signal detection, Prometheus/Grafana monitoring |
| **Stack** | Python, DuckDB, Parquet, Streamlit, Plotly, Docker, Azure, Kafka, Prometheus, Grafana |

## How it works

1. **Load and clean.** Keep the latest version of each case, use drugs reported as primary suspect, strip salts from ingredient names, and use MedDRA preferred terms for reactions.
2. **Score** every drug and reaction pair with disproportionality statistics. A "strict" flag requires the Evans rule (at least 3 cases, PRR of at least 2, chi-square of at least 4), an ROR lower bound above 1, and IC025 above 0.
3. **Validate** against known JAK inhibitor risks, using active comparators (adalimumab, etanercept, infliximab, golimumab, certolizumab, abatacept, tocilizumab, sarilumab) as the background.
4. **Replay** the data one quarter at a time to see when each signal would first have appeared.
5. **Model time to onset** with Weibull fits (shape below 1 means events cluster early).
6. **Stream** the most recent quarter report by report through Kafka and detect emerging signals live (see [Real-time extension](#real-time-extension)).

## Results

ROR against active comparators, with 95% confidence interval:

| Risk group | Tofacitinib | Upadacitinib | Baricitinib |
|---|---|---|---|
| Thrombosis / embolism | 1.70 (1.62-1.79) | 2.54 (2.41-2.67) | 8.59 (7.86-9.39) |
| Herpes zoster | 2.85 (2.72-3.00) | 2.15 (2.02-2.29) | 3.36 (2.88-3.92) |
| Heart attack / stroke | 1.41 (1.33-1.48) | 1.51 (1.42-1.61) | 2.05 (1.74-2.41) |
| Raised cholesterol | 4.65 (4.41-4.90) | 2.38 (2.20-2.57) | 2.30 (1.82-2.91) |
| Malignancy | 0.79 (0.76-0.83) | 1.55 (1.49-1.62) | 2.52 (2.26-2.81) |
| Serious infection | 0.74 (0.72-0.77) | 0.99 (0.95-1.03) | 1.61 (1.46-1.77) |

**What the results show**

- The method recovers the documented class risks: thrombosis, herpes zoster, raised cholesterol, and heart attack or stroke.
- Tofacitinib malignancy and serious infection are not elevated against the comparators. Several comparators carry their own infection and malignancy warnings, so this is a limit of the comparison, not evidence of safety. Against all other drugs, tofacitinib serious infection is elevated (ROR 1.16).
- **Replay:** baricitinib signals for thrombosis, herpes zoster, serious infection, and heart attack or stroke were first flagged in 2018 Q3, within about a quarter of its 2018 US launch. Upadacitinib malignancy was first flagged in 2022 Q1 and stayed flagged from 2023 Q3. Tofacitinib signals are mostly present from the start of the window because the drug was on the market years earlier, so the replay cannot show when they first appeared.
- **Time to onset** (cases with valid start and event dates): events cluster early, with Weibull shape below 1 for every group (0.45 to 0.96). Baricitinib thrombosis has a median of 8 days. Malignancy appears much later (median 354 to 522 days for upadacitinib and tofacitinib).

Full tables are in [`docs/results/`](docs/results/).

## Real-time extension

A streaming pipeline that replays the latest quarter (2026 Q2, 422K reports) against an 11.9M-report baseline and recalculates PRR and chi-square for JAK inhibitors as each report arrives. Using the Evans rule and excluding non-clinical terms (product issues, dosing errors, off-label use), it flagged **169 emerging signals** at about **370 reports/sec**, with Prometheus metrics and a live Grafana dashboard.

The live screen is deliberately a wider net than the batch analysis: it monitors all eleven JAK inhibitors with the Evans rule, while the batch pipeline applies the strict flag (Evans plus ROR lower bound and IC025) for confirmation.

![Live signal monitor](streaming/dashboard.png)

Code, run instructions and limitations: [`streaming/`](streaming/README.md).

## Architecture

```
FDA FAERS quarterly files
        |
        v
Load      src/download.py, sanitize.py, load.py   ->  raw tables in DuckDB
        |
        v
Clean     src/clean.py                            ->  cases, case_ps, case_reaction
        |
        +-----> Stream   streaming/producer.py    ->  Kafka topic faers-reports
        |                streaming/consumer.py    ->  live PRR / chi-square, new signals
        |                                             to Kafka topic faers-signals
        |                Prometheus + Grafana     ->  live monitoring dashboard
        v
Score     src/signals.py                          ->  PRR, ROR, chi-square, IC025
        |
        v
Validate  src/validate.py, backtest.py, onset.py  ->  validation, replay, time to onset
        |
        v
Export    src/export_app_data.py                  ->  app_data/ for the dashboard
        |
        v
Upload    src/upload_azure.py                     ->  Azure Blob Storage (Data Lake Gen2)
        |
        v
Package   Dockerfile                              ->  Streamlit + Plotly image
        |
        v
Deploy    Azure Container Registry                ->  Azure Container Apps (public dashboard)
```

**Azure components**

- **Blob Storage (Data Lake Gen2):** cleaned Parquet tables (about 520 MB) and result files in `processed/clean` and `processed/results`.
- **Container Registry:** stores the dashboard image, built for linux/amd64.
- **Container Apps:** serves the Streamlit dashboard publicly. The image bundles a filtered copy of the results (`app_data/`), so the dashboard does not read from Blob Storage at runtime.

**Streaming components**

- **Kafka:** `faers-reports` carries incoming reports; `faers-signals` carries newly flagged signals.
- **Prometheus:** scrapes throughput, report counts, signals flagged, and PRR and case counts for the top emerging signals.
- **Grafana:** live dashboard (`streaming/grafana-dashboard.json`).

## Run it locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m src.download 2024q4          # one quarter; see src/download.py for ranges
python -m src.load && python -m src.clean && python -m src.signals
python -m src.validate && python -m src.backtest && python -m src.onset
python -m src.export_app_data

streamlit run app.py
```

Docker:

```bash
docker build -t drug-safety-app .
docker run --rm -p 8501:8000 drug-safety-app
```

Streaming extension:

```bash
cd streaming
docker compose up -d            # Kafka, Prometheus, Grafana
python consumer.py              # wait for "Ready"
python producer.py 500          # second terminal; argument = reports/sec
```

Tests: `python -m pytest`

## Limitations

- **Voluntary reports, no denominators.** These are reporting ratios, not risks or incidence rates.
- **Confounding by indication.** Patients on these drugs have rheumatoid arthritis and related disease, which causes some of the reported events. The dashboard still shows indication-related and screening terms (for example tuberculin test positive, finger deformity, joint lock, spinal operation).
- **Stimulated reporting.** Media attention and safety communications raise reporting and can inflate signals after warnings.
- **No multiple-testing correction** across the many drug and reaction pairs. Signals are hypotheses.
- **Case handling.** Primary-suspect drugs only; deleted cases are not removed; ingredient normalization is rule-based.
- **Risk groups** are keyword-based groupings of MedDRA terms, not official MedDRA standardized queries.
- **Comparator choice.** Rituximab was removed from the comparators because it treats lymphoma, which inflated the malignancy background.
- **Time to onset** uses only cases with valid start and event dates and does not account for censoring.
- **Streaming is a simulated replay** of historical FAERS data, not a production feed, and its counts are held in memory.
- **Disproportionality methods detect signals.** They do not establish causation.
