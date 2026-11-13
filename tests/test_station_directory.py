import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path
from scripts.station_directory import neighbours,point,EARTH_METRES,write_directory,city_from_description

class StationDirectoryTests(unittest.TestCase):
    def test_precomputed_cutoff_names_and_exact_station(self):
        latitude=31.7;longitude=35.2
        stations={
            'a':{'name':'מרכז','point':(latitude,longitude)},
            'b':{'name':'התחנה הנגדית','point':(latitude+math.degrees(299.9999/EARTH_METRES),longitude)},
            'c':{'name':'מחוץ לטווח','point':(latitude+math.degrees(300.01/EARTH_METRES),longitude)},
            'd':{'name':'מיקום חסר','point':None},
        }
        result=neighbours(stations)
        self.assertEqual([row[0] for row in result['a']],['b'])
        self.assertEqual(result['a'][0][2],300)
        self.assertEqual(result['d'],[])
        self.assertNotIn('a',[row[0] for row in result['a']])
    def test_directory_supports_inventory_stops_without_bus_service(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            count=write_directory(root,{'s1':('100','מרכז','31.7','35.2'),'s2':('101','רכבת','31.7001','35.2')},{'100':[['1','route','מסלול','a','מפעיל','s1','מרכז','0']]},'2026-11-13','now')
            self.assertEqual(count,2)
            meta=json.loads((root/'stations'/(hashlib.sha256(b'101').hexdigest()[:20]+'.json')).read_text())
            self.assertEqual(meta['routes'],[])
            self.assertEqual(meta['nearby'][0][0],'100')
            self.assertEqual([row[:2] for row in json.loads((root/'station-search.json').read_text())['stops']],[['100','מרכז'],['101','רכבת']])
    def test_platforms_are_one_choice_but_distinct_variants_stay_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            stops={'a':('100','מרכז','31.7','35.2'),'b':('100','מרכז','31.7','35.2'),'opposite':('101','מרכז','31.7001','35.2')}
            choices={'100':[['1','route','שם','3','אגד','b','מרכז','0','11-1-0','0'],['1','route','שם','3','אגד','a','מרכז','0','11-1-0','0'],['1','alternative','שם','3','אגד','a','מרכז','א','11-1-א','0']]}
            write_directory(root,stops,choices,'day','now')
            data=json.loads((root/'stations'/(hashlib.sha256(b'100').hexdigest()[:20]+'.json')).read_text())
            self.assertEqual(len(data['routes']),2)
            row=next(r for r in data['routes'] if r[1]=='route')
            self.assertEqual(row[5],'a');self.assertEqual(row[10],['a','b'])
            self.assertTrue(all('opposite' not in r[10] for r in data['routes']))
    def test_city_is_official_metadata_not_a_name_guess(self):
        self.assertEqual(city_from_description('רחוב: נחל שקמה 12 עיר: שדרות רציף:  קומה: '),'שדרות')
        self.assertEqual(city_from_description('עיר: תל אביב יפו'),'תל אביב יפו')
        self.assertEqual(city_from_description('תחנה מרכזית ירושלים'),'')
    def test_bad_coordinates_are_not_invented(self):
        self.assertIsNone(point('nan','35'))
        self.assertIsNone(point('91','35'))
        self.assertIsNone(point(None,None))
