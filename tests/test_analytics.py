import sqlite3
import unittest

from telecom_ai.analytics import OPERATOR_COLOURS, analyze_question, chart_svg
from telecom_ai.database import initialize
from telecom_ai.ingest import metric_key, normalize_text
from telecom_ai.openapi import action_schema


class AnalyticsTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        initialize(self.connection)
        label = "Total Mobile Cellular Voice Subscriptions(Prepaid &Postpaid)"
        for operator, workbook_hash, values in (
            ("MTN", "mtn", (("2025-01", 100.0), ("2026-01", 120.0), ("2026-07", 132.0))),
            ("AirtelTigo", "at", (("2025-01", 80.0), ("2026-01", 90.0), ("2026-07", 99.0))),
        ):
            workbook_id = self.connection.execute(
                """
                INSERT INTO source_workbooks(
                    operator, source_archive, file_name, file_sha256, sheet_name,
                    imported_at_utc, external_link_count, month_headers_json
                ) VALUES (?, 'sample.zip', ?, ?, 'Monthly', '2026-01-01T00:00:00+00:00', 0, '[]')
                """,
                (operator, f"{operator}.xlsx", workbook_hash),
            ).lastrowid
            metric_id = self.connection.execute(
                """
                INSERT INTO metrics(
                    canonical_key, canonical_name, normalized_name, section,
                    definition, unit, first_seen_workbook_id
                ) VALUES (?, ?, ?, 'Subscriptions', '', 'Numbers', ?)
                """,
                (metric_key(label, f"Subscriptions {operator}", "Numbers"), label, normalize_text(label), workbook_id),
            ).lastrowid
            for index, (period, value) in enumerate(values, 1):
                self.connection.execute(
                    """
                    INSERT INTO observations(
                        source_workbook_id, metric_id, operator, period, value_numeric,
                        value_text, value_status, source_cell, raw_label, has_formula
                    ) VALUES (?, ?, ?, ?, ?, ?, 'numeric', ?, ?, 0)
                    """,
                    (workbook_id, metric_id, operator, period, value, str(value), f"A{index}", label),
                )
        self.connection.commit()

    def tearDown(self):
        self.connection.close()

    def test_analysis_returns_statistics_series_and_svg(self):
        result = analyze_question(
            self.connection,
            "Compare MTN and AirtelTigo voice subscriptions from 2025 to July 2026",
        )
        self.assertEqual(len(result["analysis"]["statistics"]), 2)
        self.assertEqual(len(result["chart"]["series"]), 2)
        self.assertIn("<svg", result["chart_svg"])
        self.assertEqual(result["analysis"]["statistics"][1]["operator"], "MTN")
        self.assertEqual(result["analysis"]["statistics"][1]["percent_change"], 32.0)
        self.assertEqual(result["governance"]["data_transfer"], "structured_aggregate_if_called_by_external_gpt_action")

    def test_empty_chart_is_accessible_svg(self):
        svg = chart_svg({"title": "Empty", "series": []})
        self.assertIn("No numeric series available", svg)
        self.assertIn('role="img"', svg)

    def test_action_schema_has_read_only_analysis_operation(self):
        schema = action_schema("https://analytics.example.org/")
        self.assertEqual(schema["servers"][0]["url"], "https://analytics.example.org")
        operation = schema["paths"]["/api/v1/analysis/query"]["post"]
        self.assertEqual(operation["operationId"], "analyzeTelecomData")
        self.assertIn("apiKey", schema["components"]["securitySchemes"])

    def test_operator_colours_are_stable(self):
        self.assertEqual(OPERATOR_COLOURS["MTN"], "#ffcb05")
        self.assertEqual(OPERATOR_COLOURS["AirtelTigo"], "#1976d2")
        self.assertEqual(OPERATOR_COLOURS["Telecel"], "#e31b23")

    def test_chart_series_include_operator_colours(self):
        result = analyze_question(
            self.connection,
            "Compare MTN and AirtelTigo voice subscriptions from 2025 to July 2026",
        )
        colours = {item["name"]: item["colour"] for item in result["chart"]["series"]}
        self.assertEqual(colours, {"AirtelTigo": "#1976d2", "MTN": "#ffcb05"})


if __name__ == "__main__":
    unittest.main()
