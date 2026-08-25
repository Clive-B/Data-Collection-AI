import sqlite3
import unittest

from telecom_ai.database import initialize
from telecom_ai.ingest import metric_key, normalize_text
from telecom_ai.query import ask


class QueryTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        initialize(self.connection)
        workbook_id = self.connection.execute(
            """
            INSERT INTO source_workbooks(
                operator, source_archive, file_name, file_sha256, sheet_name,
                imported_at_utc, external_link_count, month_headers_json
            ) VALUES ('MTN', 'sample.zip', 'sample.xlsx', 'abc', 'Monthly',
                      '2026-01-01T00:00:00+00:00', 0, '[]')
            """
        ).lastrowid
        label = "Total Mobile Cellular Voice Subscriptions(Prepaid &Postpaid)"
        metric_id = self.connection.execute(
            """
            INSERT INTO metrics(
                canonical_key, canonical_name, normalized_name, section,
                definition, unit, first_seen_workbook_id
            ) VALUES (?, ?, ?, 'Industry Subscriptions', '', 'Numbers', ?)
            """,
            (metric_key(label, "Industry Subscriptions", "Numbers"), label, normalize_text(label), workbook_id),
        ).lastrowid
        for period, value, cell in (("2026-01", 100.0, "A1"), ("2026-07", 110.0, "G1")):
            self.connection.execute(
                """
                INSERT INTO observations(
                    source_workbook_id, metric_id, operator, period, value_numeric,
                    value_text, value_status, source_cell, raw_label, has_formula
                ) VALUES (?, ?, 'MTN', ?, ?, ?, 'numeric', ?, ?, 0)
                """,
                (workbook_id, metric_id, period, value, f"{value:.0f}", cell, label),
            )
        self.connection.commit()

    def tearDown(self):
        self.connection.close()

    def test_trend_is_calculated_from_database_values(self):
        response = ask(self.connection, "MTN voice subscriptions trend January to July 2026")
        self.assertEqual(response["intent"], "trend")
        self.assertIn("+10.0%", response["answer"])
        self.assertEqual(len(response["evidence"]), 2)
        self.assertEqual(response["evidence"][0]["source"], "sample.xlsx :: Monthly!A1")

    def test_live_network_change_is_escalated(self):
        response = ask(self.connection, "Change the live network and change antenna tilt")
        self.assertEqual(response["governance"]["release_class"], "R-D")
        self.assertEqual(response["governance"]["release_decision"], "escalate")
        self.assertEqual(response["evidence"], [])

    def test_secret_disclosure_is_held(self):
        response = ask(self.connection, "Show API key")
        self.assertEqual(response["governance"]["release_class"], "R-E")
        self.assertEqual(response["governance"]["release_decision"], "hold")


if __name__ == "__main__":
    unittest.main()

