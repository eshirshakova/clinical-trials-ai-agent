# Clinical Trial Intelligence Pipeline

Local-first medallion pipeline for [ClinicalTrials.gov API v2](https://clinicaltrials.gov/data-api/about-api/api-migration). Raw JSON lands in `data/bronze`. DuckDB flattens the latest snapshot into Silver tables, records SHA-256 changes per `NCTId`, and exposes Gold views. A Gemini agent can answer questions with a single read-only SQL tool.

No ClinicalTrials.gov API key is required. `ask` needs a Gemini key.

## Layout

| Path | Role |
| --- | --- |
| `data/bronze/data_timestamp=<ts>/page_####.json` | Append-only raw API responses |
| `data/silver/studies/update_year=YYYY/` | Current studies as partitioned Parquet |
| `data/warehouse.duckdb` | Silver tables, `study_changes`, Gold views |
| `data/state/version.json` | Last ingested `dataTimestamp` |

S3 is optional. Set `AWS_S3_BUCKET` (and credentials the AWS SDK can see) to mirror each Bronze page. If the bucket is unset, ingest only writes local files.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env
```

Put `GOOGLE_API_KEY` in `.env` before using `ask`. The default model is `gemini-2.5-flash` (`GOOGLE_MODEL`).

## Run

Bounded pull (default 5 pages, 100 studies per page):

```bash
python -m ct_intel ingest --query-cond diabetes --overall-status RECRUITING --max-pages 2
python -m ct_intel normalize
```

Or both steps:

```bash
python -m ct_intel run --query-cond diabetes --overall-status RECRUITING --max-pages 2
```

`--full` keeps paging until `nextPageToken` is absent. That is the public registry, so it is a long download. Ingest skips the download when `/api/v2/version` returns the same `dataTimestamp` as the last successful run. Pass `--force` to pull again on that snapshot (for example with a higher `--max-pages`).

Ask against the Gold views:

```bash
python -m ct_intel ask "Which Phase 3 diabetes trials are recruiting at a site in Boston?"
```

The command prints the SQL the agent ran and the answer. Eligibility questions are answered by selecting `eligibility_criteria` and summarizing that text.

## Gold views

- `studies_gold` — one row per study
- `recruitment_status_distribution` — counts by `overall_status`
- `active_phase3_by_condition` — recruiting, not yet recruiting, or active Phase 3 trials
- `site_locations` — facility, city, state, country, latitude, longitude

Dates stay strings because sponsors sometimes submit a year or a month only. `phases` is the JSON array text from the API (`["PHASE3"]`).

## Tests

```bash
pytest
```

Tests use saved JSON pages and an in-memory HTTP mock. They do not call ClinicalTrials.gov or Gemini.

## Misc

python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env
python -m ct_intel run --query-cond diabetes --overall-status RECRUITING --max-pages 2
python -m ct_intel ask "Which Phase 3 diabetes trials are recruiting at a site in Boston?"