import unittest

from telecom_ai.ingest import _month_range, metric_key, normalize_section, normalize_text


class IngestHelpersTest(unittest.TestCase):
    def test_normalize_text_handles_spacing_and_ampersand(self):
        self.assertEqual(normalize_text(" Prepaid  &Postpaid "), "prepaid and postpaid")

    def test_section_number_does_not_change_metric_identity(self):
        first = metric_key("Call Drop Rate", "4. Network Parameters", "Numbers")
        second = metric_key("Call Drop Rate", "5. Network Parameters", "Numbers")
        self.assertEqual(first, second)
        self.assertEqual(normalize_section("4. Network Parameters"), "network parameters")

    def test_month_range_crosses_year(self):
        self.assertEqual(_month_range("2025-11", "2026-02"), ["2025-11", "2025-12", "2026-01", "2026-02"])


if __name__ == "__main__":
    unittest.main()

