"""Production pipeline integration: real ZIPs, state restoration and revisions."""
import contextlib
import csv
import gzip
import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
from unittest.mock import patch
from scripts.changes_pipeline import run, previous_month
from scripts.change_bundle import validate
from test_changes_gtfs import make_zip

TODAY=date(2026,11,13)


def rewrite(path, transform):
    with zipfile.ZipFile(path) as z:
        tables={name:list(csv.DictReader(io.StringIO(z.read(name).decode()))) for name in z.namelist()}
    transform(tables)
    with zipfile.ZipFile(path,'w') as z:
        for name,rows in tables.items():
            if not rows: continue
            b=io.StringIO();w=csv.DictWriter(b,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
            z.writestr(name,b.getvalue())


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.zip=self.root/'feed.zip';self.state=self.root/'state.sqlite.gz';self.output=self.root/'changes'
        make_zip(self.zip)
    def tearDown(self): self.tmp.cleanup()
    def process(self,today=TODAY):
        with contextlib.redirect_stdout(io.StringIO()):
            return run(self.zip,self.state,self.output,today,'2026-11-13T12:00:00+02:00')
    def events(self,station='123'):
        path=self.output/'stations'/(hashlib.sha256(station.encode()).hexdigest()[:20]+'.json')
        return json.loads(path.read_text())['changes'] if path.exists() else []
    def test_baseline_repeated_run_and_new_dates_are_not_changes(self):
        first=self.process();second=self.process(date(2026,11,14))
        self.assertEqual(first['stats']['events'],0);self.assertEqual(second['stats']['events'],0)
        validate(self.root)
    def test_schedule_revision_revert_and_duplicate_suppression(self):
        self.process();make_zip(self.zip,departure='08:02:00');self.process()
        first=self.events()[0];self.assertEqual(first['type'],'schedule_changed')
        self.assertEqual(first['after']['first'],8*3600+120)
        self.process();self.assertEqual(first,self.events()[0])
        make_zip(self.zip);self.process();revert=self.events()[0]
        self.assertEqual(revert['revision'],2);self.assertEqual(revert['supersedes'],first['id'])
        self.assertNotEqual(revert['id'],first['id']);self.assertEqual(revert['after']['first'],8*3600)
    def test_route_added_removed_stops(self):
        self.process();make_zip(self.zip,extra_stop=True);self.process()
        self.assertEqual(self.events()[0]['type'],'route_changed')
        self.assertEqual(self.events()[0]['addedStops'],['125'])
        self.assertEqual(self.events('125')[0]['type'],'added')
        make_zip(self.zip);self.process()
        self.assertIn(['125','Third'],self.events()[0]['removedStops'])
        self.assertEqual(self.events('125')[0]['type'],'removed')
    def test_identifier_churn_and_names_do_not_change_identity(self):
        self.process()
        def transform(t):
            t['routes.txt'][0]['route_id']='newroute'
            t['trips.txt'][0].update(route_id='newroute',trip_id='newtrip')
            for r in t['stop_times.txt']:r['trip_id']='newtrip'
            for table in ['stops.txt','stop_times.txt']:
                for r in t[table]:r['stop_id']='new'+r['stop_id']
            t['stops.txt'][0]['stop_name']='Renamed'
        rewrite(self.zip,transform);self.process();self.assertEqual(self.events(),[])
    def test_overnight_0230_and_2630_same_transport_day(self):
        make_zip(self.zip,departure='02:30:00');self.process()
        def transform(t):
            # 02:30 of service day D is 26:30 of the preceding day.
            for r in t['calendar.txt']:
                r['start_date']='20261031';r['end_date']='20261230'
            t['calendar_dates.txt'][0]['date']='20261113'
            t['stop_times.txt'][0]['departure_time']='26:30:00'
        rewrite(self.zip,transform);self.process()
        # Second stop remains 08:10 and intentionally changes dates at boundaries;
        # the first stop has precisely the same transport-day departures.
        self.assertEqual(self.events(),[])
    def test_weekdays_and_exceptions_are_not_adjacent_day_changes(self):
        def transform(t):
            t['calendar.txt'][0]['saturday']='0'
        rewrite(self.zip,transform);self.process();self.process(date(2026,11,15));self.assertEqual(self.events(),[])
    def test_calendar_exception_only_and_unbounded_future_horizon(self):
        def transform(t):
            del t['calendar.txt']
            t['calendar_dates.txt']=[dict(service_id='s',date='20261113',exception_type='1'),dict(service_id='s',date='20271113',exception_type='1')]
        rewrite(self.zip,transform);index=self.process();self.assertEqual(index['end'],'2027-11-13')
    def test_failure_does_not_overwrite_valid_state_or_output(self):
        self.process();state=self.state.read_bytes();index=(self.output/'index.json').read_bytes()
        self.zip.write_bytes(b'not a zip')
        with self.assertRaises(zipfile.BadZipFile):self.process()
        self.assertEqual(self.state.read_bytes(),state);self.assertEqual((self.output/'index.json').read_bytes(),index)
    def test_missing_trip_times_rejected(self):
        self.process();before=self.state.read_bytes()
        rewrite(self.zip,lambda t:t['trips.txt'].append(dict(t['trips.txt'][0],trip_id='incomplete')))
        with self.assertRaisesRegex(ValueError,'missing stop times'):self.process()
        self.assertEqual(self.state.read_bytes(),before)
    def test_historical_service_disappearing_is_not_cancellation(self):
        self.process()
        rewrite(self.zip,lambda t:t['calendar.txt'][0].update(start_date='20261114'))
        self.process(date(2026,11,14))
        self.assertFalse(any(e['date']<'2026-11-14' for e in self.events()))
    def test_expiration_and_calendar_month(self):
        self.assertEqual(previous_month(date(2026,3,31)),date(2026,2,28))
        self.process();make_zip(self.zip,departure='08:02:00');self.process();self.process(date(2026,12,15))
        self.assertTrue(all(e['date']>='2026-11-15' for e in self.events()))
    def test_atomic_restore_bundle(self):
        from scripts.change_bundle import main
        self.process()
        bundle=self.root/'bundle.zip';dest=self.root/'restored'
        with patch('sys.argv',['bundle','bundle',str(self.root),str(bundle)]):main()
        with patch('sys.argv',['bundle','restore',str(bundle),str(dest)]):main()
        self.assertEqual((dest/'state.sqlite.gz').read_bytes(),self.state.read_bytes())
        validate(dest)
