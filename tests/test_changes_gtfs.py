"""Small synthetic GTFS fixtures: no network or external dependencies."""
import csv
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
from scripts.build_changes import snapshot, compare

def make_zip(path, departure="08:00:00", extra_stop=False):
    tables={
      "agency.txt":(["agency_id","agency_name"],[["A","Operator"]]),
      "routes.txt":(["route_id","agency_id","route_type","route_short_name"],[["r","A","3","4"]]),
      "trips.txt":(["route_id","service_id","trip_id","direction_id"],[["r","s","t","0"]]),
      "stops.txt":(["stop_id","stop_code","stop_name"],[["s1","123","First"],["s2","124","Second"]]+([["s3","125","Third"]] if extra_stop else [])),
      "calendar.txt":(["service_id","start_date","end_date","monday","tuesday","wednesday","thursday","friday","saturday","sunday"],[["s","20261101","20261231","1","1","1","1","1","1","1"]]),
      "calendar_dates.txt":(["service_id","date","exception_type"],[["s","20261114","2"]]),
      "stop_times.txt":(["trip_id","stop_sequence","stop_id","departure_time"],[["t","1","s1",departure],["t","2","s2","08:10:00"]]+([["t","3","s3","08:20:00"]] if extra_stop else []))
    }
    with zipfile.ZipFile(path,"w") as z:
        for name,(header,rows) in tables.items():
            from io import StringIO
            buf=StringIO();w=csv.writer(buf);w.writerow(header);w.writerows(rows)
            z.writestr(name,buf.getvalue())

class SyntheticGtfsTests(unittest.TestCase):
    def test_calendar_exception_removes_service(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"test.zip";make_zip(path)
            result=snapshot(path,[date(2026,11,13),date(2026,11,14)])
            self.assertIn("123",result["2026-11-13"])
            self.assertNotIn("123",result["2026-11-14"])

    def test_departure_change_only_affects_station(self):
        with tempfile.TemporaryDirectory() as td:
            a=Path(td)/"a.zip";b=Path(td)/"b.zip"
            make_zip(a,"08:00:00");make_zip(b,"08:02:00")
            old=snapshot(a,[date(2026,11,13)])
            new=snapshot(b,[date(2026,11,13)])
            changes=compare(old,new,"2026-11-13")
            self.assertEqual(changes["123"][0]["type"],"schedule_changed")
            self.assertNotIn("124",changes)

    def test_route_added_stop(self):
        with tempfile.TemporaryDirectory() as td:
            a=Path(td)/"a.zip";b=Path(td)/"b.zip"
            make_zip(a);make_zip(b,extra_stop=True)
            old=snapshot(a,[date(2026,11,13)])
            new=snapshot(b,[date(2026,11,13)])
            changes=compare(old,new,"2026-11-13")
            self.assertEqual(changes["123"][0]["type"],"route_changed")
            self.assertEqual(changes["123"][0]["addedStops"],["125"])

if __name__=="__main__":unittest.main()
