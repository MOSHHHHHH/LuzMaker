#!/usr/bin/env python3
"""Small offline fixture to validate Israel GTFS service days and calendar exceptions."""
import csv
import io
import json
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_gtfs import build


def csv_bytes(headers, data):
    f = io.StringIO()
    writer = csv.DictWriter(f, fieldnames=headers, lineterminator="\n")
    writer.writeheader()
    writer.writerows(data)
    return f.getvalue().encode("utf-8")


class TestGtfs(unittest.TestCase):
    def test_0300_day_and_date_exceptions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zpath = root / "fixture.zip"
            routes = [{"route_id": str(i), "route_short_name": str(i),
                       "route_long_name": f"route {i}", "route_type": "3",
                       "agency_id": "a"} for i in range(100, 121)]
            trips = [{"trip_id": f"trip-{i}", "route_id": str(i), "service_id": "s5",
                      "direction_id": "0"} for i in range(100, 121)]
            trips.extend([
                {"trip_id": "early-next", "route_id": "100", "service_id": "s6", "direction_id": "0"},
                {"trip_id": "late-25", "route_id": "100", "service_id": "s5", "direction_id": "0"},
                {"trip_id": "late-27", "route_id": "100", "service_id": "s5", "direction_id": "0"},
            ])
            stops = [{"stop_id":"A","stop_name":"Sample Stop","stop_code":"1001"}]
            times = [{"trip_id": f"trip-{i}", "stop_id": "A",
                      "stop_sequence": "1", "departure_time": "12:00:00"} for i in range(100, 121)]
            times.extend([
                {"trip_id":"early-next","stop_id":"A","stop_sequence":"1","departure_time":"02:59:00"},
                {"trip_id":"late-25","stop_id":"A","stop_sequence":"1","departure_time":"26:59:00"},
                {"trip_id":"late-27","stop_id":"A","stop_sequence":"1","departure_time":"27:00:00"},
            ])
            content = {
                "agency.txt": (["agency_id","agency_name"], [{"agency_id":"a","agency_name":"Agency"}]),
                "routes.txt": (["route_id","route_short_name","route_long_name","route_type","agency_id"], routes),
                "trips.txt": (["trip_id","route_id","service_id","direction_id"], trips),
                "stops.txt": (["stop_id","stop_name","stop_code"], stops),
                "stop_times.txt": (["trip_id","stop_id","stop_sequence","departure_time"], times),
                "calendar_dates.txt": (["service_id","date","exception_type"], [
                    {"service_id":"s5","date":"20261105","exception_type":"1"},
                    {"service_id":"s6","date":"20261106","exception_type":"1"},
                    {"service_id":"s5","date":"20261106","exception_type":"2"},
                ])
            }
            with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
                for filename, (headers, records) in content.items():
                    z.writestr(filename, csv_bytes(headers, records))
            out = root / "site"
            build(zpath, out, date(2026, 11, 5))
            idx = json.loads((out/"data"/"index.json").read_text())
            self.assertEqual(idx["start"], "2026-11-05")
            self.assertEqual(len(idx["lines"]), 21)
            filename = dict(idx["lines"])["100"]
            line = json.loads((out/"data"/"lines"/filename).read_text())
            records = line["routes"][0]["t"]["A"]
            pairs = {(mask, m) for mask, *minutes in records for m in minutes}
            self.assertIn((1, 1619), pairs)  # 02:59 on Nov 6 -> Nov 5
            self.assertIn((1, 1619), pairs)  # 26:59 on Nov 5 -> Nov 5
            self.assertIn((2, 180), pairs)   # 27:00 on Nov 5 -> Nov 6
            self.assertIn((1, 720), pairs)   # noon on Nov 5
            self.assertNotIn((2, 720), pairs)  # service Nov 6 explicitly removed


if __name__ == "__main__":
    unittest.main()
