"""Weekly passenger semantics, latest-covered-day retention, and precise tags."""
import contextlib
import gzip
import io
import json
import sqlite3
import unittest
from datetime import date
import test_changes_pipeline as pipeline_tests
from test_changes_pipeline import rewrite
from scripts.weekly_changes import describe, difference


def profile(times,routes=None):
    return {'departures':times,'routes':routes or ['route']}


class TagTests(unittest.TestCase):
    def test_add_early_late_and_moved_edges(self):
        schedule,route,tags=describe(profile([30000,40000]),profile([20000,30000,40000,50000]))
        self.assertTrue(schedule);self.assertFalse(route)
        self.assertIn('נוספו נסיעות מוקדמות יותר ביום זה',tags)
        self.assertIn('נוספו נסיעות מאוחרות יותר ביום זה',tags)
        self.assertIn('הנסיעה הראשונה ביום זה תצא מוקדם יותר',tags)
        self.assertIn('הנסיעה האחרונה ביום זה תצא מאוחר יותר',tags)
        self.assertFalse(any('/' in t or '\\' in t for t in tags))
    def test_moved_edges_do_not_claim_added_trip_identity(self):
        _,_,tags=describe(profile([30000,40000]),profile([29000,39000]))
        self.assertIn('הנסיעה האחרונה ביום זה תצא מוקדם יותר',tags)
        self.assertNotIn('נוספו נסיעות מוקדמות יותר ביום זה',tags)
        self.assertNotIn('מספר הנסיעות גדל',tags)
    def test_internal_change_same_edges_and_count(self):
        _,_,tags=describe(profile([30000,35000,40000]),profile([30000,36000,40000]))
        self.assertIn('לוח הזמנים השתנה',tags)
        self.assertFalse(any('הראשונה' in t or 'האחרונה' in t for t in tags))
    def test_simultaneous_departures_preserve_multiplicity(self):
        self.assertEqual(difference([30000,30000],[30000]),([],[30000]))
        self.assertIn('מספר הנסיעות קטן',describe(profile([30000,30000]),profile([30000]))[2])
    def test_route_only_does_not_claim_schedule_change(self):
        schedule,route,tags=describe(profile([30000],['old']),profile([30000],['new']))
        self.assertFalse(schedule);self.assertTrue(route);self.assertEqual(tags,['המסלול השתנה'])


class CoverageTests(unittest.TestCase):
    setUp = pipeline_tests.PipelineTests.setUp
    tearDown = pipeline_tests.PipelineTests.tearDown
    process = pipeline_tests.PipelineTests.process
    events = pipeline_tests.PipelineTests.events
    # Reuse real ZIP setup without inheriting the general test suite twice.
    def test_shorter_latest_feed_retains_future_days(self):
        self.process()
        rewrite(self.zip,lambda t:t['calendar.txt'][0].update(end_date='20261120'))
        self.process()
        with gzip.open(self.state,'rb') as f:raw=f.read()
        path=self.root/'inspect.db';path.write_bytes(raw)
        with sqlite3.connect(path) as db:
            masks=[int(row[0],16) for row in db.execute('SELECT days FROM coverage')]
        self.assertTrue(any(mask & (1 << (date(2026,12,31)-date(2026,10,13)).days) for mask in masks))
        self.assertEqual({e['date'] for e in self.events()},{'2026-11-14','2026-11-21'})
    def test_two_publications_can_supply_a_weekly_pair(self):
        self.process()
        from test_changes_gtfs import make_zip
        make_zip(self.zip,departure='09:00:00')
        rewrite(self.zip,lambda t:t['calendar.txt'][0].update(start_date='20261114'))
        with contextlib.redirect_stdout(io.StringIO()):
            from scripts.changes_pipeline import run
            run(self.zip,self.state,self.output,date(2026,11,14),'2026-11-14T12:00:00+02:00')
        event=next(e for e in self.events() if e['date']=='2026-11-20')
        self.assertEqual(event['before']['first'],28800);self.assertEqual(event['after']['first'],32400)
        self.assertNotEqual(event['beforePublication'],event['afterPublication'])
    def test_v3_state_migrates_without_reset(self):
        self.process()
        path=self.root/'old.db'
        with gzip.open(self.state,'rb') as f:path.write_bytes(f.read())
        with sqlite3.connect(path) as db:
            db.execute('DROP TABLE coverage');db.execute("UPDATE meta SET value='3' WHERE key='version'")
        with gzip.open(self.state,'wb') as f:f.write(path.read_bytes())
        self.assertEqual(self.process()['version'],4)
        self.assertEqual({e['date'] for e in self.events()},{'2026-11-14','2026-11-21'})

    def test_removed_overnight_shift_does_not_overwrite_partial_edge(self):
        from test_changes_gtfs import make_zip
        make_zip(self.zip,departure='02:30:00');self.process()
        make_zip(self.zip,departure='08:00:00');self.process()
        # December 31 would require Jan 1 service to prove the removed night
        # departure. Keep its last fully covered observation instead.
        self.assertFalse(any(e['date']=='2026-12-31' for e in self.events()))

    def test_return_to_original_schedule_is_a_second_weekly_update(self):
        def temporary_change(t):
            t['calendar_dates.txt']=[]
            t['calendar.txt'][0]['end_date']='20261116'
            t['calendar.txt'].append(dict(t['calendar.txt'][0],service_id='temporary',start_date='20261117',end_date='20261123'))
            t['calendar.txt'].append(dict(t['calendar.txt'][0],service_id='return',start_date='20261124',end_date='20261231'))
            for service,trip,clock in [('temporary','temp','09:00:00'),('return','back','08:00:00')]:
                t['trips.txt'].append(dict(t['trips.txt'][0],service_id=service,trip_id=trip))
                t['stop_times.txt'].extend([dict(r,trip_id=trip,departure_time=clock if r['stop_id']=='s1' else '09:10:00' if service=='temporary' else '08:10:00') for r in list(t['stop_times.txt']) if r['trip_id']=='t'])
        rewrite(self.zip,temporary_change);self.process()
        events={e['date']:e for e in self.events()}
        self.assertEqual(events['2026-11-17']['after']['first'],32400)
        self.assertEqual(events['2026-11-24']['after']['first'],28800)
        self.assertIn('הנסיעה הראשונה ביום זה תצא מוקדם יותר',events['2026-11-24']['tags'])
