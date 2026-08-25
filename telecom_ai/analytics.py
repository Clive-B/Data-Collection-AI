from __future__ import annotations

import html
import json
import math
import sqlite3
import statistics
from collections import defaultdict
from datetime import date
from hashlib import sha256
from typing import Any

from .query import ask


SERIES_COLOURS = ("#172743", "#d3a33c", "#26735b", "#9a6513", "#334b88")


def _month_index(period: str) -> int:
    year, month = (int(part) for part in period.split("-", 1))
    return year * 12 + month - 1


def _safe_percent(change: float, base: float) -> float | None:
    if base == 0:
        return None
    return change / abs(base) * 100


def _round(value: float | None, digits: int = 4) -> float | None:
    return None if value is None or not math.isfinite(value) else round(value, digits)


def _series_from_evidence(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, float]] = defaultdict(dict)
    for item in evidence:
        value = item.get("numeric_value")
        if value is not None:
            grouped[str(item["operator"])][str(item["period"])] = float(value)
    return [
        {
            "name": operator,
            "points": [{"period": period, "value": values[period]} for period in sorted(values)],
        }
        for operator, values in sorted(grouped.items())
    ]


def _detect_anomalies(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(points) < 7:
        return []
    changes: list[tuple[str, float]] = []
    for previous, current in zip(points, points[1:]):
        if _month_index(current["period"]) - _month_index(previous["period"]) != 1:
            continue
        percent = _safe_percent(current["value"] - previous["value"], previous["value"])
        if percent is not None:
            changes.append((current["period"], percent))
    if len(changes) < 6:
        return []
    median = statistics.median(value for _, value in changes)
    deviations = [abs(value - median) for _, value in changes]
    mad = statistics.median(deviations)
    if mad == 0:
        return []
    robust_scale = 1.4826 * mad
    return [
        {
            "period": period,
            "change_percent": _round(value, 2),
            "robust_z_score": _round((value - median) / robust_scale, 2),
            "method": "period-over-period change beyond 3 robust standard deviations",
        }
        for period, value in changes
        if abs((value - median) / robust_scale) >= 3
    ]


def _series_statistics(series: dict[str, Any]) -> dict[str, Any]:
    points = series["points"]
    if not points:
        return {"operator": series["name"], "observations": 0}
    first, last = points[0], points[-1]
    absolute_change = last["value"] - first["value"]
    percent_change = _safe_percent(absolute_change, first["value"])
    periods = _month_index(last["period"]) - _month_index(first["period"])
    cagr = None
    if periods >= 12 and first["value"] > 0 and last["value"] >= 0:
        cagr = ((last["value"] / first["value"]) ** (12 / periods) - 1) * 100

    point_map = {point["period"]: point["value"] for point in points}
    previous_year_index = _month_index(last["period"]) - 12
    previous_year_period = f"{previous_year_index // 12:04d}-{previous_year_index % 12 + 1:02d}"
    yoy = None
    if previous_year_period in point_map:
        yoy = _safe_percent(last["value"] - point_map[previous_year_period], point_map[previous_year_period])

    period_changes = []
    for previous, current in zip(points, points[1:]):
        if _month_index(current["period"]) - _month_index(previous["period"]) != 1:
            continue
        change = _safe_percent(current["value"] - previous["value"], previous["value"])
        if change is not None:
            period_changes.append(change)

    return {
        "operator": series["name"],
        "observations": len(points),
        "first_period": first["period"],
        "last_period": last["period"],
        "first_value": first["value"],
        "last_value": last["value"],
        "absolute_change": _round(absolute_change),
        "percent_change": _round(percent_change, 2),
        "latest_year_over_year_percent": _round(yoy, 2),
        "cagr_percent": _round(cagr, 2),
        "average_period_change_percent": _round(statistics.fmean(period_changes), 2) if period_changes else None,
        "minimum": _round(min(point["value"] for point in points)),
        "maximum": _round(max(point["value"] for point in points)),
        "anomalies": _detect_anomalies(points),
    }


def _insights(statistics_rows: list[dict[str, Any]]) -> list[str]:
    insights: list[str] = []
    for row in statistics_rows:
        if row.get("observations", 0) < 2:
            continue
        direction = "increased" if row["absolute_change"] > 0 else "decreased" if row["absolute_change"] < 0 else "was unchanged"
        percent = row.get("percent_change")
        suffix = f" ({percent:+.2f}%)" if percent is not None else ""
        insights.append(
            f"{row['operator']} {direction} from {row['first_value']:,.4g} in {row['first_period']} "
            f"to {row['last_value']:,.4g} in {row['last_period']}{suffix}."
        )
        if row.get("latest_year_over_year_percent") is not None:
            insights.append(
                f"{row['operator']}'s latest year-over-year change was {row['latest_year_over_year_percent']:+.2f}%."
            )
        if row.get("anomalies"):
            periods = ", ".join(item["period"] for item in row["anomalies"][:5])
            insights.append(f"{row['operator']} has statistically unusual period changes at {periods}; verify source context.")
    if len(statistics_rows) >= 2:
        latest = [row for row in statistics_rows if row.get("last_value") is not None]
        if len(latest) >= 2 and len({row["last_period"] for row in latest}) == 1:
            leader = max(latest, key=lambda row: row["last_value"])
            insights.append(f"{leader['operator']} had the highest reported value in {leader['last_period']} among the compared operators.")
    return insights


def _chart_spec(series: list[dict[str, Any]], metric: str | None) -> dict[str, Any]:
    return {
        "type": "line",
        "title": metric or "Telecom metric analysis",
        "x_axis": {"field": "period", "label": "Reporting period"},
        "y_axis": {"field": "value", "label": metric or "Reported value", "zero_baseline": True},
        "series": series,
        "accessibility_summary": f"Line chart with {len(series)} operator series.",
    }


def chart_svg(chart: dict[str, Any], width: int = 960, height: int = 480) -> str:
    series = chart.get("series", [])
    points = [point for item in series for point in item.get("points", [])]
    if not points:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" role="img">'
            '<rect width="100%" height="100%" fill="#fffdf8"/><text x="50%" y="50%" '
            'text-anchor="middle" fill="#526074" font-family="sans-serif">No numeric series available</text></svg>'
        )
    periods = sorted({point["period"] for point in points})
    values = [float(point["value"]) for point in points]
    minimum, maximum = min(values), max(values)
    padding = (maximum - minimum) * 0.08 or max(abs(maximum) * 0.08, 1)
    y_min = 0 if minimum >= 0 else minimum - padding
    y_max = maximum + padding
    left, right, top, bottom = 90, 28, 58, 68
    plot_width, plot_height = width - left - right, height - top - bottom

    def x(period: str) -> float:
        return left + periods.index(period) * plot_width / max(1, len(periods) - 1)

    def y(value: float) -> float:
        return top + (y_max - value) * plot_height / max(1e-12, y_max - y_min)

    title = html.escape(str(chart.get("title", "Telecom analysis")))
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="{title}">',
        '<rect width="100%" height="100%" rx="18" fill="#fffdf8"/>',
        f'<text x="{left}" y="30" fill="#172743" font-family="Georgia,serif" font-size="20">{title}</text>',
    ]
    for tick in range(5):
        value = y_min + (y_max - y_min) * tick / 4
        y_pos = y(value)
        svg.append(f'<line x1="{left}" y1="{y_pos:.1f}" x2="{width-right}" y2="{y_pos:.1f}" stroke="#e4dfd5"/>')
        svg.append(f'<text x="{left-10}" y="{y_pos+4:.1f}" text-anchor="end" fill="#526074" font-family="sans-serif" font-size="11">{value:,.4g}</text>')
    label_step = max(1, math.ceil(len(periods) / 10))
    for index, period in enumerate(periods):
        if index % label_step == 0 or index == len(periods) - 1:
            svg.append(f'<text x="{x(period):.1f}" y="{height-bottom+25}" text-anchor="middle" fill="#526074" font-family="sans-serif" font-size="11">{html.escape(period)}</text>')
    for index, item in enumerate(series):
        colour = SERIES_COLOURS[index % len(SERIES_COLOURS)]
        coordinates = " ".join(f'{x(point["period"]):.1f},{y(float(point["value"])):.1f}' for point in item["points"])
        svg.append(f'<polyline points="{coordinates}" fill="none" stroke="{colour}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>')
        for point in item["points"]:
            svg.append(f'<circle cx="{x(point["period"]):.1f}" cy="{y(float(point["value"])):.1f}" r="3" fill="{colour}"><title>{html.escape(item["name"])} {html.escape(point["period"])}: {point["value"]:,.6g}</title></circle>')
        legend_x = left + index * 150
        svg.append(f'<circle cx="{legend_x}" cy="{height-18}" r="5" fill="{colour}"/><text x="{legend_x+10}" y="{height-14}" fill="#162133" font-family="sans-serif" font-size="12">{html.escape(item["name"])}</text>')
    svg.append('</svg>')
    return "".join(svg)


def analyze_question(connection: sqlite3.Connection, question: str) -> dict[str, Any]:
    response = ask(connection, question)
    evidence = response.get("evidence", [])
    series = _series_from_evidence(evidence)
    stats = [_series_statistics(item) for item in series]
    metric = evidence[0].get("metric") if evidence else None
    chart = _chart_spec(series, metric)
    analysis_id = sha256(json.dumps({"question": question, "series": series}, sort_keys=True).encode()).hexdigest()[:16]
    response.update(
        {
            "analysis_id": analysis_id,
            "analysis": {
                "metric": metric,
                "statistics": stats,
                "insights": _insights(stats),
                "methodology": [
                    "Calculations use the latest retained observation for each operator, metric, and period.",
                    "Percentage changes use the absolute starting value as denominator; zero denominators are reported as unavailable.",
                    "Anomalies use a robust median-absolute-deviation test on consecutive percentage changes and require at least seven observations.",
                    "An anomaly is a review signal, not proof of an error or causal event.",
                ],
                "limitations": [
                    "Workbook definitions and reporting practices may change over time.",
                    "Missing periods are not interpolated.",
                    "Regulatory or operational conclusions require human review.",
                ],
            },
            "chart": chart,
            "chart_svg": chart_svg(chart),
            "generated_on": date.today().isoformat(),
        }
    )
    response["governance"]["data_transfer"] = "structured_aggregate_if_called_by_external_gpt_action"
    return response


def metric_catalogue(connection: sqlite3.Connection, limit: int = 200) -> dict[str, Any]:
    limit = max(1, min(limit, 500))
    rows = connection.execute(
        """
        SELECT m.normalized_name AS id, MIN(m.canonical_name) AS name,
               MIN(NULLIF(m.unit, '')) AS unit, MIN(NULLIF(m.definition, '')) AS definition,
               MIN(o.period) AS first_period, MAX(o.period) AS last_period,
               COUNT(DISTINCT o.period) AS periods, COUNT(DISTINCT o.operator) AS operator_count
        FROM metrics m LEFT JOIN observations o ON o.metric_id = m.id
        GROUP BY m.normalized_name ORDER BY name LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return {"metrics": [dict(row) for row in rows], "count": len(rows), "limit": limit}


def quality_summary(connection: sqlite3.Connection) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT severity, issue_code, COUNT(*) AS count
        FROM quality_issues GROUP BY severity, issue_code
        ORDER BY CASE severity WHEN 'error' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END, count DESC
        """
    ).fetchall()
    return {
        "findings": [dict(row) for row in rows],
        "total": sum(row["count"] for row in rows),
        "interpretation": "Quality findings are disclosure flags; review source context before regulatory use.",
    }
