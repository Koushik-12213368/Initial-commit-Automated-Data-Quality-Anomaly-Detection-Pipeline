# Automated Data Quality & Anomaly Detection Pipeline

Standalone operational tool that screens raw daily transactional / activity dumps **before** they feed management reports.

Maps to: data validation, reconciliation checks, Python automation, and exception reporting.

## What it does

1. **Validation framework** (`src/validation/`)
   - Field standardization — dates → ISO-8601, category maps → uppercase canonicals, trimmed IDs
   - Range / boundary checks — scores outside 0–100%, negative tenure/hours, etc.
   - Statistical anomaly detection — Z-score and IQR fences on metrics such as daily logins and test duration
2. **Automated discrepancy reporting** — Excel summary + CSV of exceptions and publishable clean rows
3. **Exception dashboard** — Streamlit drill-down with error codes and remediation steps

## Project layout

```
config/rules.yaml          # thresholds & mappings (no code changes needed)
data/sample_daily_activity.csv
data/expected_counts.json
src/validation/            # standardize, range, anomaly, missing, reconcile
src/reporting/             # Excel / CSV discrepancy reports
src/db/                    # SQLite (PostgreSQL-ready) persistence
src/remediation/           # error-code catalog + remediation text
dashboard/app.py           # Streamlit exception dashboard
run_pipeline.py            # CLI entry point
```

## Setup

```bash
cd "Automated Data Quality & Anomaly Detection Pipeline"
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## Run the pipeline (CLI)

```bash
python run_pipeline.py
```

Custom dump:

```bash
python run_pipeline.py -i path/to/daily_dump.csv --prior-count 30
```

Artifacts land in `outputs/`:

| File | Contents |
|------|----------|
| `*_discrepancy_summary.xlsx` | Overview, by error code, all exceptions, metric stats, reconciliation |
| `*_exceptions.csv` | Row-level exceptions with severity + remediation |
| `*_clean_records.csv` | Rows without CRITICAL/HIGH issues (safe to publish) |
| `dq_pipeline.db` | SQLite store of runs & exceptions |

## Exception dashboard

```bash
streamlit run dashboard/app.py
```

- Re-run on sample data or upload a CSV from the sidebar
- Filter by severity / error code / field
- Expand the remediation catalog for ops playbooks

## Hosting (public URL)

### Quick public tunnel (this machine must stay on)

With the dashboard already running on port 8501:

```bash
.\tools\cloudflared.exe tunnel --url http://localhost:8501
```

Cloudflare prints a public `https://*.trycloudflare.com` URL.

### Always-on cloud (recommended)

**Streamlit Community Cloud**
1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Deploy → pick the repo → Main file path: `dashboard/app.py`

**Render**
1. Push this repo to GitHub
2. Connect at [render.com](https://render.com) using the included `render.yaml`
3. Render sets `$PORT`; the start command is already configured

## Error codes (summary)

| Code | Severity | Meaning |
|------|----------|---------|
| `MISS_KEY_FIELD` | CRITICAL | Required key null/blank |
| `RECON_COUNT_LOW` / `HIGH` | CRITICAL / HIGH | Volume outside expected band |
| `RANGE_BELOW_MIN` / `ABOVE_MAX` | HIGH | Boundary violation |
| `DUP_TRANSACTION_ID` | HIGH | Duplicate primary key |
| `ANOMALY_ZSCORE` / `IQR` | MEDIUM | Statistical outlier |
| `STD_DATE_PARSE` / `CATEGORY_UNKNOWN` | HIGH / MEDIUM | Standardization failure |
| `STD_ID_WHITESPACE` | LOW | Auto-trimmed identifier |

Tune all thresholds in `config/rules.yaml`.

## Tech stack

Python · pandas · numpy · openpyxl · PyYAML · SQLite (optional PostgreSQL) · Streamlit · Plotly
