import tempfile
import unittest
import zipfile
from pathlib import Path

from telecom_ai.ingest import _month_range, _operator_for_archive, _prepare_sources, metric_key, normalize_section, normalize_text


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

    def test_operator_detection_includes_telecel_and_rejects_unknown(self):
        self.assertEqual(_operator_for_archive(Path("MTN August 2026.xlsx")), "MTN")
        self.assertEqual(_operator_for_archive(Path("AT August 2026.zip")), "AirtelTigo")
        self.assertEqual(_operator_for_archive(Path("Telecel August 2026.xlsb")), "Telecel")
        self.assertEqual(_operator_for_archive(Path("Vodafone historical.zip")), "Telecel")
        with self.assertRaises(ValueError):
            _operator_for_archive(Path("monthly report.xlsx"))

    def test_prepare_sources_accepts_direct_excel_and_zip(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            direct = root / "Telecel August 2026.xlsx"
            direct.write_bytes(b"workbook")
            archive = root / "MTN August 2026.zip"
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("nested/MTN August 2026.xlsb", b"workbook")
            prepared = _prepare_sources([direct, archive], root / "prepared")
            self.assertEqual([item[2] for item in prepared], ["Telecel", "MTN"])
            self.assertTrue((prepared[0][1] / direct.name).exists())
            self.assertTrue((prepared[1][1] / "MTN August 2026.xlsb").exists())


if __name__ == "__main__":
    unittest.main()
