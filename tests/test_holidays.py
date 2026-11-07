"""Hebcal holiday snapshot: pure mapping and mocked HTTP integration tests."""
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from scripts import build_holidays


class HolidayBuildTests(unittest.TestCase):
    def test_event_labels(self):
        cases = {
            "Erev Rosh Hashana": "ערב ראש השנה",
            "Rosh Hashana 5787": "ראש השנה",
            "Pesach VII": "שביעי של פסח",
            "Pesach III (CH'M)": "חול המועד פסח",
            "Sukkot II (CH'M)": "חול המועד סוכות",
            "Tzom Gedaliah": "צום גדליה",
            "Yom HaAtzma'ut": "יום העצמאות",
            "Yom HaZikaron": "יום הזיכרון",
            "Yom HaShoah": "יום השואה",
            "Sigd": "סיגד",
            "Daf Yomi": None,
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(build_holidays.label(title), expected)

    def test_snapshot_uses_israel_and_supported_locale(self):
        received = []

        def mocked_urlopen(request, timeout):
            url = request.full_url
            query = parse_qs(urlsplit(url).query)
            self.assertEqual(query["i"], ["on"])
            self.assertEqual(query["lg"], ["s"])
            self.assertEqual(query["start"], ["2026-11-07"])
            self.assertEqual(query["end"], ["2026-11-26"])
            received.append(url)
            data = {
                "items": [
                    {"date": "2026-11-09", "title": "Sigd"},
                    {"date": "2026-11-09", "title": "Daf Yomi"},
                    {"date": "2026-11-18", "title": "Yom HaZikaron"},
                ]
            }
            return io.BytesIO(json.dumps(data).encode("utf-8"))

        with tempfile.TemporaryDirectory() as temp, patch.object(build_holidays.urllib.request, "urlopen", mocked_urlopen):
            output = Path(temp) / "holidays.json"
            build_holidays.generate(date(2026, 11, 7), 20, output)
            snapshot = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(snapshot["source"], "Hebcal.com")
            self.assertEqual(snapshot["events"]["2026-11-09"], ["סיגד"])
            self.assertEqual(snapshot["events"]["2026-11-18"], ["יום הזיכרון"])
            self.assertEqual(len(received), 1)


if __name__ == "__main__":
    unittest.main()
