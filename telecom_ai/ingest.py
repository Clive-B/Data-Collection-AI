from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import tempfile
import unicodedata
import zipfile
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from .database import connect, initialize


SPACE_RE = re.compile(r"\s+")
LEADING_NUMBER_RE = re.compile(r"^\s*\d{1,2}(?:\s*[a-z])?[\s.():-]+", re.I)


def normalize_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "").casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9%]+", " ", text)
    return SPACE_RE.sub(" ", text).strip()


def normalize_section(value: str | None) -> str:
    return normalize_text(LEADING_NUMBER_RE.sub("", value or ""))


def metric_key(label: str, section: str, unit: str) -> str:
    identity = "|".join((normalize_section(section), normalize_text(label), normalize_text(unit)))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _operator_for_archive(path: Path) -> str:
    return "MTN" if "mtn" in path.name.casefold() else "AirtelTigo"


def _extract_archives(archives: Iterable[Path], destination: Path) -> list[tuple[Path, Path, str]]:
    extracted: list[tuple[Path, Path, str]] = []
    for archive in archives:
        operator = _operator_for_archive(archive)
        target = destination / operator
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as package:
            for member in package.infolist():
                member_name = Path(member.filename)
                if member.is_dir() or member_name.suffix.casefold() not in {".xls", ".xlsx", ".xlsb"}:
                    continue
                safe_name = member_name.name
                output_path = target / safe_name
                with package.open(member) as source, output_path.open("wb") as output:
                    shutil.copyfileobj(source, output)
                extracted.append((archive, output_path, operator))
    return extracted


def _run_excel_extractor(
    extracted_root: Path,
    archive: Path,
    operator: str,
    script_path: Path,
    output_path: Path,
) -> None:
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-InputDirectory",
        str(extracted_root / operator),
        "-OutputFile",
        str(output_path),
        "-Operator",
        operator,
        "-SourceArchive",
        archive.name,
    ]
    subprocess.run(command, check=True)


def _load_records(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid extractor output at {path}:{line_number}: {exc}") from exc


def _insert_issue(
    connection: sqlite3.Connection,
    workbook_id: int | None,
    severity: str,
    code: str,
    message: str,
    context: dict[str, Any] | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO quality_issues(source_workbook_id, severity, issue_code, message, context_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (workbook_id, severity, code, message, json.dumps(context or {}, sort_keys=True)),
    )


def _insert_extractor_records(
    connection: sqlite3.Connection,
    records: Iterable[dict[str, Any]],
    extracted_directory: Path,
) -> None:
    current_workbook_id: int | None = None
    current_file = ""
    label_counts: Counter[tuple[str, str]] = Counter()
    workbook_stats: dict[int, Counter[str]] = defaultdict(Counter)

    for record in records:
        record_type = record.get("type")
        if record_type == "error":
            _insert_issue(
                connection,
                None,
                "error",
                "EXTRACTION_FAILED",
                f"Could not extract {record.get('file_name')}: {record.get('message')}",
            )
            continue

        if record_type == "workbook":
            if current_workbook_id is not None:
                _finalize_workbook_quality(connection, current_workbook_id, label_counts, workbook_stats[current_workbook_id])
            current_file = record["file_name"]
            label_counts = Counter()
            workbook_path = extracted_directory / record["operator"] / current_file
            digest = file_sha256(workbook_path)
            months = record.get("months", [])
            cursor = connection.execute(
                """
                INSERT INTO source_workbooks(
                    operator, source_archive, file_name, file_sha256, sheet_name,
                    imported_at_utc, external_link_count, month_headers_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_sha256, sheet_name) DO UPDATE SET
                    imported_at_utc = excluded.imported_at_utc,
                    external_link_count = excluded.external_link_count,
                    month_headers_json = excluded.month_headers_json
                RETURNING id
                """,
                (
                    record["operator"],
                    record["source_archive"],
                    current_file,
                    digest,
                    record["sheet_name"],
                    datetime.now(UTC).isoformat(),
                    int(record.get("external_link_count", 0)),
                    json.dumps(months, sort_keys=True),
                ),
            )
            current_workbook_id = int(cursor.fetchone()[0])
            connection.execute("DELETE FROM observations WHERE source_workbook_id = ?", (current_workbook_id,))
            connection.execute("DELETE FROM quality_issues WHERE source_workbook_id = ?", (current_workbook_id,))
            if not months:
                _insert_issue(connection, current_workbook_id, "error", "NO_MONTH_COLUMNS", "No reporting month columns were detected.")
            if record.get("external_link_count", 0):
                _insert_issue(
                    connection,
                    current_workbook_id,
                    "warning",
                    "EXTERNAL_LINKS",
                    f"Workbook declares {record['external_link_count']} external link(s); cached values may be stale.",
                )
            _check_filename_period(connection, current_workbook_id, current_file, months)
            continue

        if record_type != "metric_row" or current_workbook_id is None:
            continue
        if record.get("file_name") != current_file:
            raise ValueError("Extractor records are out of workbook order")

        label = SPACE_RE.sub(" ", record.get("label", "")).strip()
        section = SPACE_RE.sub(" ", record.get("section", "")).strip()
        definition = SPACE_RE.sub(" ", record.get("definition", "")).strip()
        unit = SPACE_RE.sub(" ", record.get("unit", "")).strip()
        key = metric_key(label, section, unit)
        label_counts[(normalize_section(section), normalize_text(label))] += 1
        connection.execute(
            """
            INSERT INTO metrics(
                canonical_key, canonical_name, normalized_name, section,
                definition, unit, first_seen_workbook_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(canonical_key) DO UPDATE SET
                definition = CASE
                    WHEN length(excluded.definition) > length(COALESCE(metrics.definition, '')) THEN excluded.definition
                    ELSE metrics.definition END,
                unit = CASE WHEN excluded.unit <> '' THEN excluded.unit ELSE metrics.unit END
            """,
            (key, label, normalize_text(label), section, definition, unit, current_workbook_id),
        )
        metric_id = int(connection.execute("SELECT id FROM metrics WHERE canonical_key = ?", (key,)).fetchone()[0])

        for value in record.get("values", []):
            numeric = value.get("value_numeric")
            text = value.get("value_text") or None
            status = value.get("value_status", "blank")
            formula = (value.get("formula_text") or "")[:2000] or None
            connection.execute(
                """
                INSERT OR REPLACE INTO observations(
                    source_workbook_id, metric_id, operator, period, value_numeric,
                    value_text, value_status, source_cell, raw_label, has_formula, formula_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    current_workbook_id,
                    metric_id,
                    record.get("operator") or connection.execute(
                        "SELECT operator FROM source_workbooks WHERE id = ?", (current_workbook_id,)
                    ).fetchone()[0],
                    value["period"],
                    numeric,
                    text,
                    status,
                    value["source_cell"],
                    label,
                    int(bool(value.get("has_formula"))),
                    formula,
                ),
            )
            workbook_stats[current_workbook_id][status] += 1

    if current_workbook_id is not None:
        _finalize_workbook_quality(connection, current_workbook_id, label_counts, workbook_stats[current_workbook_id])


def _check_filename_period(
    connection: sqlite3.Connection,
    workbook_id: int,
    file_name: str,
    months: list[dict[str, Any]],
) -> None:
    years_in_name = {int(value) for value in re.findall(r"20\d{2}", file_name)}
    years_in_data = {int(item["period"][:4]) for item in months if item.get("period")}
    if years_in_name and years_in_data and years_in_name.isdisjoint(years_in_data):
        _insert_issue(
            connection,
            workbook_id,
            "warning",
            "FILENAME_PERIOD_MISMATCH",
            f"Filename suggests {sorted(years_in_name)}, but detected reporting periods are {sorted(years_in_data)}.",
            {"filename_years": sorted(years_in_name), "data_years": sorted(years_in_data)},
        )

    normalized_name = file_name.casefold().replace(" ", "")
    expected_count = None
    if "jan-dec" in normalized_name:
        expected_count = 12
    elif "jan-july" in normalized_name or "jan-jul" in normalized_name:
        expected_count = 7
    elif "jan-sept" in normalized_name or "jan-sep" in normalized_name:
        expected_count = 9
    elif "oct-dec" in normalized_name:
        expected_count = 3
    if expected_count is not None and years_in_name:
        named_year = max(years_in_name)
        actual = len({item["period"] for item in months if item.get("period", "").startswith(f"{named_year:04d}-")})
        if actual < expected_count:
            _insert_issue(
                connection,
                workbook_id,
                "warning",
                "INCOMPLETE_FILE_RANGE",
                f"Filename implies {expected_count} month(s) in {named_year}, but only {actual} were detected.",
                {"expected_months": expected_count, "detected_months": actual, "year": named_year},
            )


def _finalize_workbook_quality(
    connection: sqlite3.Connection,
    workbook_id: int,
    label_counts: Counter[tuple[str, str]],
    stats: Counter[str],
) -> None:
    duplicates = [label for (_, label), count in label_counts.items() if count > 1]
    if duplicates:
        _insert_issue(
            connection,
            workbook_id,
            "warning",
            "DUPLICATE_METRIC_LABEL",
            f"Detected {len(duplicates)} duplicated metric label(s) within the same section.",
            {"examples": duplicates[:10]},
        )
    total = sum(stats.values())
    blank = stats.get("blank", 0)
    if total and blank / total >= 0.20:
        _insert_issue(
            connection,
            workbook_id,
            "warning",
            "HIGH_BLANK_RATE",
            f"{blank / total:.1%} of extracted metric/month cells are blank.",
            dict(stats),
        )
    if stats.get("text", 0):
        _insert_issue(
            connection,
            workbook_id,
            "info",
            "TEXT_VALUES",
            f"Detected {stats['text']} textual values in reporting cells (for example N/A or notes).",
            dict(stats),
        )
    if stats.get("error", 0):
        _insert_issue(
            connection,
            workbook_id,
            "error",
            "CELL_ERRORS",
            f"Detected {stats['error']} Excel error values.",
            dict(stats),
        )


def _global_quality_checks(connection: sqlite3.Connection) -> None:
    connection.execute("DELETE FROM quality_issues WHERE source_workbook_id IS NULL AND issue_code != 'EXTRACTION_FAILED'")
    connection.execute(
        "DELETE FROM quality_issues WHERE issue_code IN ('FILENAME_PERIOD_MISMATCH', 'INCOMPLETE_FILE_RANGE')"
    )
    for workbook in connection.execute(
        "SELECT id, file_name, month_headers_json FROM source_workbooks"
    ).fetchall():
        _check_filename_period(
            connection,
            workbook["id"],
            workbook["file_name"],
            json.loads(workbook["month_headers_json"]),
        )

    for row in connection.execute(
        """
        SELECT operator, MIN(period) AS first_period, MAX(period) AS last_period
        FROM observations GROUP BY operator
        """
    ):
        periods = {
            item[0]
            for item in connection.execute(
                "SELECT DISTINCT period FROM observations WHERE operator = ?", (row["operator"],)
            )
        }
        expected = _month_range(row["first_period"], row["last_period"])
        missing = sorted(set(expected) - periods)
        if missing:
            _insert_issue(
                connection,
                None,
                "warning",
                "OPERATOR_PERIOD_GAPS",
                f"{row['operator']} has {len(missing)} missing reporting month(s) between {row['first_period']} and {row['last_period']}.",
                {"operator": row["operator"], "missing_periods": missing},
            )

    conflicts = connection.execute(
        """
        SELECT operator, metric_id, period, COUNT(DISTINCT ROUND(value_numeric, 8)) AS value_count
        FROM observations
        WHERE value_status = 'numeric'
        GROUP BY operator, metric_id, period
        HAVING COUNT(DISTINCT ROUND(value_numeric, 8)) > 1
        """
    ).fetchall()
    if conflicts:
        _insert_issue(
            connection,
            None,
            "warning",
            "CONFLICTING_DUPLICATE_VALUES",
            f"Detected {len(conflicts)} operator/metric/month combinations with conflicting numeric values.",
            {"count": len(conflicts)},
        )

    inconsistent_units = connection.execute(
        """
        SELECT normalized_name, COUNT(DISTINCT NULLIF(TRIM(unit), '')) AS unit_count
        FROM metrics
        GROUP BY normalized_name
        HAVING COUNT(DISTINCT NULLIF(TRIM(unit), '')) > 1
        """
    ).fetchall()
    if inconsistent_units:
        _insert_issue(
            connection,
            None,
            "warning",
            "INCONSISTENT_METRIC_UNITS",
            f"Detected {len(inconsistent_units)} metric name(s) associated with multiple non-empty units.",
            {"examples": [row["normalized_name"] for row in inconsistent_units[:20]]},
        )

    currency_mismatches = connection.execute(
        """
        SELECT COUNT(*)
        FROM observations
        WHERE (value_text LIKE '%€%' OR value_text LIKE '%$%')
          AND lower(raw_label) NOT LIKE '%value%'
          AND lower(raw_label) NOT LIKE '%revenue%'
          AND lower(raw_label) NOT LIKE '%fee%'
          AND lower(raw_label) NOT LIKE '%price%'
          AND lower(raw_label) NOT LIKE '%cost%'
        """
    ).fetchone()[0]
    if currency_mismatches:
        _insert_issue(
            connection,
            None,
            "warning",
            "DISPLAY_FORMAT_MISMATCH",
            f"Detected {currency_mismatches} non-monetary observation(s) displayed with a currency symbol.",
            {"count": currency_mismatches},
        )


def _month_range(first: str, last: str) -> list[str]:
    year, month = map(int, first.split("-"))
    last_year, last_month = map(int, last.split("-"))
    result: list[str] = []
    while (year, month) <= (last_year, last_month):
        result.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year += 1
            month = 1
    return result


def ingest_archives(
    database_path: str | Path,
    archives: Iterable[str | Path],
    *,
    extractor_script: str | Path | None = None,
) -> dict[str, int]:
    archive_paths = [Path(item).resolve() for item in archives]
    missing = [str(path) for path in archive_paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Archive(s) not found: {', '.join(missing)}")

    if extractor_script is None:
        extractor_script = Path(__file__).resolve().parents[1] / "scripts" / "extract_excel.ps1"
    script_path = Path(extractor_script).resolve()

    connection = connect(database_path)
    initialize(connection)
    try:
        with tempfile.TemporaryDirectory(prefix="telecom-ai-ingest-") as temp_name:
            temp = Path(temp_name)
            extracted = _extract_archives(archive_paths, temp / "workbooks")
            if not extracted:
                raise ValueError("No supported Excel workbooks were found in the archives")
            for archive in archive_paths:
                operator = _operator_for_archive(archive)
                output = temp / f"{operator}.ndjson"
                _run_excel_extractor(temp / "workbooks", archive, operator, script_path, output)
                _insert_extractor_records(connection, _load_records(output), temp / "workbooks")
                connection.commit()
        _global_quality_checks(connection)
        connection.commit()
        return {
            "workbooks": connection.execute("SELECT COUNT(*) FROM source_workbooks").fetchone()[0],
            "metrics": connection.execute("SELECT COUNT(*) FROM metrics").fetchone()[0],
            "observations": connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0],
            "numeric_observations": connection.execute(
                "SELECT COUNT(*) FROM observations WHERE value_status = 'numeric'"
            ).fetchone()[0],
            "quality_issues": connection.execute("SELECT COUNT(*) FROM quality_issues").fetchone()[0],
        }
    finally:
        connection.close()
