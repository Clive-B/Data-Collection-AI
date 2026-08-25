from __future__ import annotations

import difflib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from .ingest import normalize_text


MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

METRIC_ALIASES = {
    "voice subscriptions": "total mobile cellular voice subscriptions prepaid and postpaid",
    "voice subscribers": "total mobile cellular voice subscriptions prepaid and postpaid",
    "mobile voice subscriptions": "total mobile cellular voice subscriptions prepaid and postpaid",
    "data subscriptions": "total mobile cellular data subscriptions",
    "data subscribers": "total mobile cellular data subscriptions",
    "mobile data subscriptions": "total mobile cellular data subscriptions",
    "mobile data traffic": "total mobile data internet volumes",
    "data traffic": "total mobile data internet volumes",
    "call drop rate": "call drop rate",
    "mobile money value": "total value of mobile money transactions ghc",
    "mobile money transaction value": "total value of mobile money transactions ghc",
    "mobile money transactions": "total volume of mobile money transactions counts",
}

RESTRICTED_DISCLOSURE = (
    "show api key",
    "reveal api key",
    "show password",
    "reveal password",
    "expose secret",
    "show access token",
)
OPERATIONAL_ACTIONS = (
    "change the live network",
    "disable the cell",
    "shut down the cell",
    "change antenna tilt",
    "change transmit power",
    "implement immediately",
    "execute the change",
)


@dataclass(frozen=True)
class Evidence:
    operator: str
    period: str
    metric: str
    displayed_value: str
    numeric_value: float | None
    source: str
    quality: str


def _operators(question: str) -> list[str]:
    lower = question.casefold()
    result: list[str] = []
    if re.search(r"\bmtn\b", lower):
        result.append("MTN")
    if "airteltigo" in lower or "airtel tigo" in lower or re.search(r"\bairtel\b", lower) or re.search(r"\bAT\b", question):
        result.append("AirtelTigo")
    return result


def _period_range(question: str) -> tuple[str | None, str | None]:
    years = [int(value) for value in re.findall(r"\b(20\d{2})\b", question)]
    month_matches = [
        MONTHS[match.group(1).casefold()]
        for match in re.finditer(
            r"\b(january|february|march|april|may|june|july|august|september|october|november|december|sept|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\b",
            question,
            re.I,
        )
    ]
    if not years:
        return None, None
    if len(years) >= 2:
        start_month = month_matches[0] if month_matches else 1
        end_month = month_matches[-1] if month_matches else 12
        return f"{years[0]:04d}-{start_month:02d}", f"{years[-1]:04d}-{end_month:02d}"
    year = years[0]
    if len(month_matches) >= 2:
        return f"{year:04d}-{month_matches[0]:02d}", f"{year:04d}-{month_matches[-1]:02d}"
    if len(month_matches) == 1:
        period = f"{year:04d}-{month_matches[0]:02d}"
        return period, period
    return f"{year:04d}-01", f"{year:04d}-12"


def _intent(question: str) -> str:
    lower = question.casefold()
    if any(term in lower for term in ("quality", "data issue", "data problem")):
        return "quality"
    if (
        any(term in lower for term in ("missing month", "coverage gap", "missing period"))
        or re.search(r"\bmissing\b.*\b(months?|periods?)\b", lower)
    ):
        return "missing_periods"
    if any(term in lower for term in ("list metrics", "available metrics", "what can i ask")):
        return "list_metrics"
    if any(term in lower for term in ("compare", "comparison", "versus", " vs ")):
        return "compare"
    if any(term in lower for term in ("trend", "change", "growth", "decline", "increase", "decrease")):
        return "trend"
    if any(term in lower for term in ("latest", "current", "most recent")):
        return "latest"
    return "lookup"


def _metric_phrase(question: str) -> str:
    lower = question.casefold()
    for alias, target in sorted(METRIC_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if alias in lower:
            return target
    cleaned = re.sub(r"\b20\d{2}\b", " ", lower)
    cleaned = re.sub("|".join(rf"\b{re.escape(month)}\b" for month in MONTHS), " ", cleaned, flags=re.I)
    cleaned = re.sub(
        r"\b(mtn|airteltigo|airtel|tigo|at|show|give|tell|me|the|a|an|compare|comparison|versus|vs|trend|change|growth|decline|increase|decrease|from|to|through|between|and|in|for|during|latest|current|most|recent|what|is|was|were|of)\b",
        " ",
        cleaned,
        flags=re.I,
    )
    return normalize_text(cleaned)


def _metric_candidates(connection: sqlite3.Connection, question: str, limit: int = 5) -> list[sqlite3.Row]:
    phrase = _metric_phrase(question)
    rows = connection.execute(
        """
        SELECT normalized_name, MIN(canonical_name) AS canonical_name, COUNT(*) AS variants
        FROM metrics GROUP BY normalized_name
        """
    ).fetchall()
    phrase_tokens = set(phrase.split())
    scored: list[tuple[float, sqlite3.Row]] = []
    for row in rows:
        name = row["normalized_name"]
        name_tokens = set(name.split())
        overlap = len(phrase_tokens & name_tokens) / max(1, len(phrase_tokens | name_tokens))
        if phrase == name:
            containment = 1.0
        elif phrase and phrase in name:
            containment = 0.94
        elif name and name in phrase:
            containment = 0.62 * min(1.0, len(name) / max(1, len(phrase)))
        else:
            containment = 0.0
        sequence = difflib.SequenceMatcher(None, phrase, name).ratio()
        score = max(containment, 0.55 * overlap + 0.45 * sequence)
        scored.append((score, row))
    scored.sort(key=lambda item: (-item[0], item[1]["canonical_name"]))
    return [row for score, row in scored[:limit] if score >= 0.22]


def _evidence_rows(
    connection: sqlite3.Connection,
    normalized_metric: str,
    operators: list[str],
    start: str | None,
    end: str | None,
    latest_only: bool,
) -> list[Evidence]:
    clauses = ["m.normalized_name = ?", "o.value_status IN ('numeric', 'text')"]
    params: list[Any] = [normalized_metric]
    if operators:
        clauses.append(f"o.operator IN ({','.join('?' for _ in operators)})")
        params.extend(operators)
    if start:
        clauses.append("o.period >= ?")
        params.append(start)
    if end:
        clauses.append("o.period <= ?")
        params.append(end)
    sql = f"""
        WITH ranked AS (
            SELECT o.*, m.canonical_name, sw.file_name, sw.sheet_name,
                   ROW_NUMBER() OVER (
                       PARTITION BY o.operator, m.normalized_name, o.period
                       ORDER BY sw.id DESC, o.id DESC
                   ) AS source_rank
            FROM observations o
            JOIN metrics m ON m.id = o.metric_id
            JOIN source_workbooks sw ON sw.id = o.source_workbook_id
            WHERE {' AND '.join(clauses)}
        )
        SELECT * FROM ranked WHERE source_rank = 1
        ORDER BY operator, period, metric_id
    """
    rows = connection.execute(sql, params).fetchall()
    if latest_only and rows:
        latest: dict[str, sqlite3.Row] = {}
        for row in rows:
            if row["operator"] not in latest or row["period"] > latest[row["operator"]]["period"]:
                latest[row["operator"]] = row
        rows = list(latest.values())
    return [
        Evidence(
            operator=row["operator"],
            period=row["period"],
            metric=row["canonical_name"],
            displayed_value=row["value_text"] or _format_number(row["value_numeric"]),
            numeric_value=row["value_numeric"],
            source=f"{row['file_name']} :: {row['sheet_name']}!{row['source_cell']}",
            quality="formula" if row["has_formula"] else "reported value",
        )
        for row in rows
    ]


def _format_number(value: float | None) -> str:
    if value is None:
        return "not available"
    if abs(value - round(value)) < 1e-9:
        return f"{value:,.0f}"
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def _answer_from_evidence(intent: str, evidence: list[Evidence]) -> str:
    if not evidence:
        return "No matching populated observations were found for the requested metric, operator, and period."
    by_operator: dict[str, list[Evidence]] = {}
    for item in evidence:
        by_operator.setdefault(item.operator, []).append(item)

    lines: list[str] = []
    for operator, items in by_operator.items():
        items.sort(key=lambda item: item.period)
        if intent == "trend" and len(items) >= 2:
            first, last = items[0], items[-1]
            delta_text = "change unavailable"
            if first.numeric_value is not None and last.numeric_value is not None:
                delta = last.numeric_value - first.numeric_value
                if first.numeric_value != 0:
                    percent = delta / abs(first.numeric_value) * 100
                    delta_text = f"a change of {_format_number(delta)} ({percent:+.1f}%)"
                else:
                    delta_text = f"a change of {_format_number(delta)}"
            lines.append(
                f"{operator}: {first.displayed_value} in {first.period} to {last.displayed_value} in {last.period}, {delta_text}."
            )
        elif intent == "compare" or len(items) == 1:
            last = items[-1]
            lines.append(f"{operator}: {last.displayed_value} in {last.period}.")
        else:
            values = ", ".join(f"{item.period}: {item.displayed_value}" for item in items)
            lines.append(f"{operator}: {values}.")
    if intent == "compare" and len(by_operator) >= 2:
        latest_values = [items[-1] for items in by_operator.values() if items[-1].numeric_value is not None]
        if len(latest_values) >= 2 and len({item.period for item in latest_values}) == 1:
            left, right = latest_values[:2]
            difference = left.numeric_value - right.numeric_value
            lines.append(f"Difference ({left.operator} minus {right.operator}): {_format_number(difference)}.")
    return " ".join(lines)


def _quality_answer(connection: sqlite3.Connection) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT severity, issue_code, COUNT(*) AS count
        FROM quality_issues GROUP BY severity, issue_code
        ORDER BY CASE severity WHEN 'error' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END, count DESC
        """
    ).fetchall()
    summary = "; ".join(f"{row['issue_code']}: {row['count']} {row['severity']}" for row in rows) or "No quality issues recorded."
    return _response(summary, "quality", [], "U2", "R-B", "release_with_caution")


def _missing_period_answer(connection: sqlite3.Connection, operators: list[str]) -> dict[str, Any]:
    rows = connection.execute(
        "SELECT message, context_json FROM quality_issues WHERE issue_code = 'OPERATOR_PERIOD_GAPS'"
    ).fetchall()
    lines = []
    for row in rows:
        context = json.loads(row["context_json"])
        if operators and context.get("operator") not in operators:
            continue
        periods = context.get("missing_periods", [])
        preview = ", ".join(periods[:24])
        if len(periods) > 24:
            preview += f", and {len(periods) - 24} more"
        lines.append(f"{context.get('operator')}: {preview}")
    answer = "Missing reporting periods - " + "; ".join(lines) if lines else "No matching period-gap record was found."
    return _response(answer, "missing_periods", [], "U2", "R-B", "release_with_caution")


def _list_metrics(connection: sqlite3.Connection) -> dict[str, Any]:
    rows = connection.execute(
        "SELECT canonical_name, COUNT(*) AS variants FROM metrics GROUP BY normalized_name ORDER BY canonical_name LIMIT 50"
    ).fetchall()
    answer = "Available metrics include: " + "; ".join(row["canonical_name"] for row in rows)
    return _response(answer, "list_metrics", [], "U1", "R-A", "release")


def _response(
    answer: str,
    intent: str,
    evidence: list[Evidence],
    uncertainty: str,
    release_class: str,
    release_decision: str,
    *,
    alternatives: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "answer": answer,
        "intent": intent,
        "evidence": [asdict(item) for item in evidence],
        "alternatives": alternatives or [],
        "governance": {
            "status": "conceptually_enforced_local_policy",
            "human_authority": "required for operational decisions",
            "uncertainty_class": uncertainty,
            "release_class": release_class,
            "release_decision": release_decision,
            "data_transfer": "none",
        },
    }


def _audit(connection: sqlite3.Connection, question: str, response: dict[str, Any], parameters: dict[str, Any]) -> None:
    summary = re.sub(r"[\w.+-]+@[\w.-]+", "[redacted-email]", question)
    summary = re.sub(r"\b\+?\d[\d\s()-]{7,}\b", "[redacted-number]", summary)[:240]
    governance = response["governance"]
    connection.execute(
        """
        INSERT INTO query_audit(
            timestamp_utc, question_summary, intent, parameters_json, evidence_count,
            governance_status, uncertainty_class, release_class
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now(UTC).isoformat(),
            summary,
            response["intent"],
            json.dumps(parameters, sort_keys=True),
            len(response["evidence"]),
            governance["status"],
            governance["uncertainty_class"],
            governance["release_class"],
        ),
    )
    connection.commit()


def ask(connection: sqlite3.Connection, question: str) -> dict[str, Any]:
    question = question.strip()
    if not question:
        return _response("A question is required.", "hold", [], "U4", "R-E", "hold")
    if len(question) > 1000:
        return _response("The question exceeds the 1,000-character limit.", "hold", [], "U4", "R-E", "hold")
    lower = question.casefold()
    if any(term in lower for term in RESTRICTED_DISCLOSURE):
        response = _response("The request seeks restricted credential or secret disclosure.", "hold", [], "U4", "R-E", "hold")
        _audit(connection, question, response, {})
        return response
    if any(term in lower for term in OPERATIONAL_ACTIONS):
        response = _response(
            "This query service cannot authorize or execute a live network change. An authorized engineer must review the evidence.",
            "operational_escalation",
            [],
            "U3",
            "R-D",
            "escalate",
        )
        _audit(connection, question, response, {})
        return response

    intent = _intent(question)
    operators = _operators(question)
    start, end = _period_range(question)
    parameters = {"operators": operators, "start": start, "end": end}
    if intent == "quality":
        response = _quality_answer(connection)
    elif intent == "missing_periods":
        response = _missing_period_answer(connection, operators)
    elif intent == "list_metrics":
        response = _list_metrics(connection)
    else:
        candidates = _metric_candidates(connection, question)
        if not candidates:
            response = _response(
                "I could not match the question to a catalogued metric. Ask for available metrics or use a more specific KPI name.",
                "clarify",
                [],
                "U4",
                "R-D",
                "escalate",
            )
        else:
            best = candidates[0]
            alternatives = [row["canonical_name"] for row in candidates[1:4]]
            if len(best["normalized_name"].split()) <= 1:
                response = _response(
                    f"The metric phrase is ambiguous. Please choose a more specific KPI, such as: {', '.join(alternatives)}.",
                    "clarify",
                    [],
                    "U4",
                    "R-D",
                    "escalate",
                    alternatives=alternatives,
                )
            else:
                parameters["metric"] = best["normalized_name"]
                evidence = _evidence_rows(
                    connection,
                    best["normalized_name"],
                    operators,
                    start,
                    end,
                    latest_only=intent == "latest" or (intent == "lookup" and start is None),
                )
                uncertainty = "U1" if evidence and all(item.numeric_value is not None for item in evidence) else "U2"
                release_class = "R-A" if uncertainty == "U1" else "R-B"
                decision = "release" if release_class == "R-A" else "release_with_caution"
                response = _response(
                    _answer_from_evidence(intent, evidence),
                    intent,
                    evidence,
                    uncertainty,
                    release_class,
                    decision,
                    alternatives=alternatives,
                )
    _audit(connection, question, response, parameters)
    return response
