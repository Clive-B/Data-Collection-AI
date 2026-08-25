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
- Derived change, year-over-year, CAGR, range, and robust anomaly statistics.
- Accessible SVG trend graphs and chart-ready JSON series.
- OpenAPI 3.1 Action contract for the Adinkra Omega Custom GPT.

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
- `GET /openapi.json` - GPT Action schema
- `POST /api/v1/analysis/query` - authenticated production Action endpoint
- `GET /api/v1/metrics` - metric catalogue and coverage
- `GET /api/v1/quality` - aggregated quality findings
- `GET /privacy` - data-use and analytical-boundary notice

The built-in HTTP server is a local-development interface, not a production deployment. Set `TELECOM_API_KEY` to enforce API-key authentication on analytical API routes. The server refuses a non-local bind without that key, but production TLS and other controls must still be supplied by an approved reverse proxy and hosting environment. A production dashboard should sit behind an authenticated proxy that injects the upstream key without exposing it to browser JavaScript.

## Connect Adinkra Omega

See [docs/ADINKRA_GPT_SETUP.md](docs/ADINKRA_GPT_SETUP.md) for deployment prerequisites, the Custom GPT instruction block, Action authentication, and the evaluation set. The public GPT link alone does not provide permission to edit its Action configuration.

## Data model

- `source_workbooks`: operator, archive, filename, SHA-256 hash, sheet, link count, detected months.
- `metrics`: canonical key, name, section, definition, and unit.
- `observations`: operator/month/value plus workbook, sheet, cell, formula, and status provenance.
- `quality_issues`: structured workbook-level and collection-level findings.
- `query_audit`: minimized question summary and release metadata; raw evidence values are not copied into the audit.

## Governance and security boundary

The MVP keeps processing and storage local and performs no external network calls. Human authority remains mandatory for operational decisions. The implementation conceptually applies data minimization, provenance, explainability, least privilege, and deny-by-default external transfer.

This is not evidence that VPF runtime services, African data residency, encryption at rest, TLS, signed binaries, certificates, PADCA/Omnis ledgers, or scheduled enforcement are technically active. Production deployment must implement and independently verify those controls. The supplied VPF configuration remains external authoritative policy and is not copied into or modified by this project.

## Test

```powershell
python -m unittest discover -s tests -v
```

## Next production steps

1. Review and approve the canonical metric mappings and known discontinuities.
2. Add authenticated role-based access and production TLS.
3. Move the SQLite model to an approved African-hosted PostgreSQL environment if concurrent use is required.
4. Add a locally hosted or residency-approved language model only as a constrained planner over the read-only query API.
5. Add signed ingestion manifests, encrypted storage, backup, retention, and independent audit enforcement.
