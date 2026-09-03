# Adinkra Omega Telecom Analytics

This repository contains a local, evidence-grounded query system for the supplied MTN and AirtelTigo monthly-report archives.

It converts mixed `.xls`, `.xlsx`, and `.xlsb` workbooks into a canonical SQLite database, retains source provenance down to the workbook/sheet/cell, records data-quality findings, and answers constrained natural-language questions with deterministic SQL calculations.

## Current capabilities

- Read-only Excel extraction with macros forcibly disabled.
- Canonical operators, metrics, periods, observations, workbook hashes, and quality issues.
- Natural-language lookup, trend, comparison, latest-value, missing-period, and quality-summary questions.
- Source evidence attached to every reported observation.
- Local query audit with basic email and phone-number redaction.
- Governance holds for credential disclosure and escalation for live-network change requests.
- Local JSON API bound to `127.0.0.1` by default.
- Embedded NCA Adinkra Omega Copilot using the OpenAI Responses API as a grounded narrative layer.
- Ongoing browser-based imports for monthly ZIP, XLS, XLSX, and XLSB submissions.
- Consistent operator colours: MTN yellow, AirtelTigo blue, and Telecel red.
- Selectable, downloadable SVG charts: line, grouped bar, area, radar, heatmap, gauge, and donut.
- Official NCA logo and `#01AFE4` institutional interface theme.
- Derived change, year-over-year, CAGR, range, and robust anomaly statistics.
- Accessible SVG trend graphs and chart-ready JSON series.
- OpenAPI 3.1 Action contract retained for optional Adinkra Omega Custom GPT access.

The query engine is intentionally not a trained model. It is the deterministic semantic, statistical, charting, and evidence layer used by the dashboard and the Adinkra Omega Custom GPT Action. Its parser chooses approved query parameters; SQLite and the analytics module perform the calculations.

## Requirements

- Windows with Microsoft Excel installed.
- Python 3.11 or later.
- No third-party Python packages are required.

## Build the local database

From this repository:

```powershell
python -m telecom_ai --database data/telecom.db ingest "MTN Monthly Data.zip" "AT's Monthly Data (2020-July 2026).zip"
```

Excel is opened invisibly and read-only. VBA macros are disabled. Temporary extracted copies are removed automatically.

The generated database is deliberately ignored by Git because it contains governed operational data.

## Ask questions

```powershell
python -m telecom_ai --database data/telecom.db ask "Show the trend in MTN voice subscriptions from January to July 2026"

python -m telecom_ai --database data/telecom.db ask "Compare MTN and AirtelTigo mobile data subscriptions in July 2026"

python -m telecom_ai --database data/telecom.db ask "Show missing reporting months for MTN"

python -m telecom_ai --database data/telecom.db quality
```

Add `--json` to an `ask` command for the complete structured answer and governance envelope.

## Local API

```powershell
python -m telecom_ai --database data/telecom.db serve
```

Open `http://127.0.0.1:8765` in a browser to use the responsive Network Intelligence Desk. The dashboard provides guided questions, dataset statistics, direct answers, source-cell evidence, related metrics, and governance indicators.

Endpoints:

- `GET /` — local dashboard
- `GET /health`
- `GET /stats`
- `GET /ask?q=Show%20latest%20MTN%20voice%20subscriptions`
- `POST /ask` with `{"question": "..."}`
- `POST /api/analysis` with `{"question": "..."}` - dashboard analysis, statistics, and SVG graph
- `POST /api/copilot` with `{"question": "..."}` - embedded NCA Adinkra Omega response grounded in local analysis
- `POST /api/data/import` - authenticated/raw workbook upload used by the dashboard's monthly import form
- `GET /openapi.json` - GPT Action schema
- `POST /api/v1/analysis/query` - authenticated production Action endpoint
- `GET /api/v1/metrics` - metric catalogue and coverage
- `GET /api/v1/quality` - aggregated quality findings
- `GET /privacy` - data-use and analytical-boundary notice

The built-in HTTP server is a local-development interface, not a production deployment. Set `TELECOM_API_KEY` to enforce API-key authentication on analytical API routes. The server refuses a non-local bind without that key, but production TLS and other controls must still be supplied by an approved reverse proxy and hosting environment. A production dashboard should sit behind an authenticated proxy that injects the upstream key without exposing it to browser JavaScript.

## Enable the embedded NCA Adinkra Omega Copilot

Create an API key in the OpenAI Platform, then set it only in the server process:

```powershell
$env:OPENAI_API_KEY = "your-api-key"
$env:OPENAI_MODEL = "gpt-5.6-luna"
python -m telecom_ai --database data/telecom.db serve
```

Do not put the key in `index.html`, `app.js`, source control, or a browser request. If `OPENAI_API_KEY` is absent or the API is unavailable, the dashboard returns the local deterministic answer and identifies it as a fallback. `OPENAI_MODEL` is optional and defaults to `gpt-5.6-luna`.

The copilot route calculates locally first. Only the question, deterministic summary, derived statistics, limitations, governance classification, and at most 60 necessary evidence references are sent to OpenAI. Requests set `store: false`. Governance holds, secret-disclosure requests, and operational-change requests are never sent to OpenAI.

## Work with charts

After running a question with numeric evidence, use the chart selector above the visualization to switch between line, bars, area, radar, heatmap, gauge, and donut views. Hover or keyboard-focus a mark for its operator, period, value, and available source; select it to highlight the matching evidence. Operator legends show or hide series, and the navigation controls zoom, pan, or reset the reporting window. The dashboard recommends a starting view based on the question intent. Each specialized view states its period or scale treatment below the chart. Select **Download SVG** to save the current accessible vector chart.

Operator identity remains stable across every view: MTN is yellow, AirtelTigo is blue, and Telecel is red. The surrounding application uses the NCA theme colour `#01AFE4`.

## Add a new reporting month

Use the **Add monthly data** panel in the dashboard:

1. Select MTN, AirtelTigo, or Telecel.
2. Choose a ZIP archive or an `.xls`, `.xlsx`, or `.xlsb` workbook.
3. Select **Import data** and keep the page open while Excel is processed.
4. Confirm the updated coverage and quality findings before using the new month in analysis.

Imports are additive. Re-uploading a corrected workbook with the same workbook filename and worksheet replaces that workbook's earlier extracted observations while preserving its provenance record. Operator selection is authoritative for browser uploads; CLI imports require MTN, AirtelTigo/AT, Telecel, or Vodafone in the submitted filename.

## Optional Custom GPT connection

See [docs/ADINKRA_GPT_SETUP.md](docs/ADINKRA_GPT_SETUP.md) for deployment prerequisites, the Custom GPT instruction block, Action authentication, and the evaluation set. The public GPT link alone does not provide permission to edit its Action configuration.

## Data model

- `source_workbooks`: operator, archive, filename, SHA-256 hash, sheet, link count, detected months.
- `metrics`: canonical key, name, section, definition, and unit.
- `observations`: operator/month/value plus workbook, sheet, cell, formula, and status provenance.
- `quality_issues`: structured workbook-level and collection-level findings.
- `query_audit`: minimized question summary and release metadata; raw evidence values are not copied into the audit.

## Governance and security boundary

The evidence engine keeps database processing and storage local. The embedded copilot makes an external OpenAI API call only through `/api/copilot`, after the local release decision permits it; all other analytical routes remain local. Human authority remains mandatory for operational decisions. The implementation applies data minimization, provenance, explainability, least privilege, and governance gating to that transfer.

This is not evidence that VPF runtime services, African data residency, encryption at rest, TLS, signed binaries, certificates, PADCA/Omnis ledgers, or scheduled enforcement are technically active. Production deployment must implement and independently verify those controls. The supplied VPF configuration remains external authoritative policy and is not copied into or modified by this project.

## Test

```powershell
python -m unittest discover -s tests -v
```

## Next production steps

1. Review and approve the canonical metric mappings and known discontinuities.
2. Add authenticated role-based access and production TLS.
3. Move the SQLite model to an approved African-hosted PostgreSQL environment if concurrent use is required.
4. Obtain custodian approval for the OpenAI project controls, permitted data classes, and cross-border transfer basis, or use a residency-approved model endpoint.
5. Add signed ingestion manifests, encrypted storage, backup, retention, and independent audit enforcement.
