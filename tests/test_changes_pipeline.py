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
    def test_baseline_includes_weekly_exception_and_resumption(self):
        first=self.process();events=self.events();self.process(date(2026,11,14))
        self.assertEqual({(e['date'],e['type']) for e in events},{('2026-11-14','removed'),('2026-11-21','added')})
        self.assertEqual(first['comparison'],'weekly')
        self.assertTrue(all((date.fromisoformat(e['date'])-date.fromisoformat(e['comparisonDate'])).days==7 for e in events))
        validate(self.root)
    def test_latest_publication_replaces_both_days_without_revision_alert(self):
        self.process();make_zip(self.zip,departure='08:02:00');self.process()
        self.assertFalse(any(e['type']=='schedule_changed' for e in self.events()))
        self.assertEqual(self.events()[0]['before']['first'],8*3600+120)
        make_zip(self.zip);self.process()
        self.assertEqual(self.events()[0]['before']['first'],8*3600)
        self.assertNotIn('revision',self.events()[0])
    def test_weekly_route_change_has_both_sequences_and_details(self):
        make_zip(self.zip,extra_stop=True)
        def change(t):
            t['calendar_dates.txt']=[]
            base=t['calendar.txt'][0];base['end_date']='20261116'
            t['calendar.txt'].append(dict(base,service_id='next',start_date='20261117',end_date='20261231'))
            t['trips.txt'].append(dict(t['trips.txt'][0],service_id='next',trip_id='next'))
            original=list(t['stop_times.txt']);t['stop_times.txt']=[r for r in original if r['stop_id']!='s3']
            t['stop_times.txt'] += [dict(r,trip_id='next') for r in original]
        rewrite(self.zip,change);self.process()
        event=next(e for e in self.events() if e['date']=='2026-11-17')
        self.assertTrue(event['routeChanged']);self.assertFalse(event['scheduleChanged'])
        self.assertEqual(event['addedStops'],['125'])
        self.assertNotEqual(event['beforeRoutes'],event['routes'])
        details=json.loads((self.output/'details'/(hashlib.sha256(b'123').hexdigest()[:20]+'.json')).read_text())
        self.assertEqual(details['profiles'][event['afterProfile']]['departures'],[28800])
        self.assertTrue(set(event['beforeRoutes']+event['routes'])<=details['routeDefinitions'].keys())
    def test_identifier_churn_and_names_do_not_change_identity(self):
        self.process()
        def transform(t):
            t['routes.txt'][0]['route_id']='newroute'
            t['trips.txt'][0].update(route_id='newroute',trip_id='newtrip')
            for r in t['stop_times.txt']:r['trip_id']='newtrip'
            for table in ['stops.txt','stop_times.txt']:
                for r in t[table]:r['stop_id']='new'+r['stop_id']
            t['stops.txt'][0]['stop_name']='Renamed'
        rewrite(self.zip,transform);self.process();self.assertFalse(any(e['type']=='schedule_changed' or e['routeChanged'] for e in self.events()))
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
        self.assertFalse(any(e['type']=='schedule_changed' or e['routeChanged'] for e in self.events()))
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
    def test_new_variant_is_not_a_publication_alert(self):
        self.process()
        def add_variant(t):
            t['routes.txt'].append(dict(t['routes.txt'][0],route_id='r2',route_short_name='6'))
            t['trips.txt'].append(dict(t['trips.txt'][0],trip_id='t2',route_id='r2'))
            t['stop_times.txt'].extend([dict(r,trip_id='t2') for r in list(t['stop_times.txt'])])
        rewrite(self.zip,add_variant);self.process()
        self.assertEqual({e['date'] for e in self.events()},{'2026-11-14','2026-11-21'})
        self.assertEqual(len(self.events()),4)
    def test_same_line_distinct_official_variants_are_not_merged(self):
        def variants(t):
            t['routes.txt'][0]['route_desc']='100-1-A'
            t['routes.txt'].append(dict(t['routes.txt'][0],route_id='r2',route_desc='100-1-B'))
            t['trips.txt'].append(dict(t['trips.txt'][0],route_id='r2',trip_id='t2'))
            t['stop_times.txt'].extend([dict(r,trip_id='t2') for r in list(t['stop_times.txt'])])
        rewrite(self.zip,variants);self.process()
        def edit(t):
            for r in t['stop_times.txt']:
                if r['trip_id']=='t2' and r['stop_id']=='s1':r['departure_time']='09:00:00'
        rewrite(self.zip,edit);self.process()
        self.assertEqual({json.loads(e['line'])[3] for e in self.events()},{'100-1-A','100-1-B'})
        self.assertFalse(any(e['type']=='schedule_changed' for e in self.events()))
    def test_latest_exception_correction_removes_outdated_alerts(self):
        self.process()
        rewrite(self.zip,lambda t:t['calendar_dates.txt'][0].update(exception_type='1'))
        self.process();self.assertEqual(self.events(),[])
    def test_partial_transport_dates_at_feed_boundaries_are_not_changes(self):
        make_zip(self.zip,departure='02:30:00');self.process()
        rewrite(self.zip,lambda t:t['calendar.txt'][0].update(start_date='20261114',end_date='20261230'))
        self.process(date(2026,11,14))
        self.assertFalse(any(e['type']=='schedule_changed' or e['routeChanged'] for e in self.events()))
        self.assertFalse(any(e['type']=='schedule_changed' for e in self.events('124')))
    def test_corrupt_historical_state_is_not_silently_reinitialized(self):
        self.process();index=(self.output/'index.json').read_bytes()
        self.state.write_bytes(b'corrupt')
        with self.assertRaises(gzip.BadGzipFile):self.process()
        self.assertEqual(index,(self.output/'index.json').read_bytes())
    def test_atomic_restore_bundle(self):
        from scripts.change_bundle import main
        self.process()
        bundle=self.root/'bundle.zip';dest=self.root/'restored'
        with patch('sys.argv',['bundle','bundle',str(self.root),str(bundle)]):main()
        with patch('sys.argv',['bundle','restore',str(bundle),str(dest)]):main()
        self.assertEqual((dest/'state.sqlite.gz').read_bytes(),self.state.read_bytes())
        validate(dest)
