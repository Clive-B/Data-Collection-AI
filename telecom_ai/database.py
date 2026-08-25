from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS source_workbooks (
    id INTEGER PRIMARY KEY,
    operator TEXT NOT NULL,
    source_archive TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_sha256 TEXT NOT NULL,
    sheet_name TEXT NOT NULL,
    imported_at_utc TEXT NOT NULL,
    external_link_count INTEGER NOT NULL DEFAULT 0,
    month_headers_json TEXT NOT NULL,
    UNIQUE(file_sha256, sheet_name)
);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY,
    canonical_key TEXT NOT NULL UNIQUE,
    canonical_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    section TEXT NOT NULL,
    definition TEXT,
    unit TEXT,
    first_seen_workbook_id INTEGER NOT NULL REFERENCES source_workbooks(id)
);

CREATE INDEX IF NOT EXISTS idx_metrics_normalized_name
ON metrics(normalized_name);

CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY,
    source_workbook_id INTEGER NOT NULL REFERENCES source_workbooks(id) ON DELETE CASCADE,
    metric_id INTEGER NOT NULL REFERENCES metrics(id),
    operator TEXT NOT NULL,
    period TEXT NOT NULL,
    value_numeric REAL,
    value_text TEXT,
    value_status TEXT NOT NULL CHECK(value_status IN ('numeric', 'text', 'blank', 'error')),
    source_cell TEXT NOT NULL,
    raw_label TEXT NOT NULL,
    has_formula INTEGER NOT NULL DEFAULT 0,
    formula_text TEXT,
    UNIQUE(source_workbook_id, metric_id, period, source_cell)
);

CREATE INDEX IF NOT EXISTS idx_observations_lookup
ON observations(operator, metric_id, period);

CREATE INDEX IF NOT EXISTS idx_observations_period
ON observations(period);

CREATE TABLE IF NOT EXISTS quality_issues (
    id INTEGER PRIMARY KEY,
    source_workbook_id INTEGER REFERENCES source_workbooks(id) ON DELETE CASCADE,
    severity TEXT NOT NULL CHECK(severity IN ('info', 'warning', 'error')),
    issue_code TEXT NOT NULL,
    message TEXT NOT NULL,
    context_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_quality_issue_code
ON quality_issues(issue_code, severity);

CREATE TABLE IF NOT EXISTS query_audit (
    id INTEGER PRIMARY KEY,
    timestamp_utc TEXT NOT NULL,
    question_summary TEXT NOT NULL,
    intent TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    evidence_count INTEGER NOT NULL,
    governance_status TEXT NOT NULL,
    uncertainty_class TEXT NOT NULL,
    release_class TEXT NOT NULL
);
"""


def connect(database_path: str | Path, *, readonly: bool = False) -> sqlite3.Connection:
    path = Path(database_path).resolve()
    if readonly:
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)
    connection.commit()

