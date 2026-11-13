"""Offline production-format data for the main UI, PDF and change-page tests."""
import contextlib
import csv
import io
import shutil
import sys
import zipfile
from datetime import date
from pathlib import Path
from scripts.build_gtfs import build
from scripts.changes_pipeline import run


def fixture(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    zpath=root/'feed.zip'
    routes=[dict(route_id=str(n),agency_id='3',route_type='3',route_short_name=str(n),route_long_name='ביתר עילית<->תל אביב (ABC)-1#',route_desc=f'11{n}-1-0') for n in range(100,121)]
    trips=[dict(route_id=str(n),service_id='s',trip_id='t'+str(n),direction_id='0') for n in range(100,121)]
    trips.append(dict(route_id='100',service_id='s',trip_id='platform2',direction_id='0'))
    stops=[dict(stop_id='A',stop_code='12345',stop_name='ת. מרכזית',stop_lat='31.7',stop_lon='35.2'),dict(stop_id='A2',stop_code='12345',stop_name='ת. מרכזית',stop_lat='31.7',stop_lon='35.2'),dict(stop_id='B',stop_code='12346',stop_name='ת. מרכזית',stop_lat='31.701',stop_lon='35.2'),dict(stop_id='C',stop_code='12347',stop_name='תחנה רחוקה',stop_lat='31.703',stop_lon='35.2'),dict(stop_id='D',stop_code='12348',stop_name='תחנה ללא שינויים',stop_lat='31.71',stop_lon='35.2')]
    calendar=[dict(service_id='s',start_date='20261113',end_date='20261231',**{day:'1' for day in 'monday tuesday wednesday thursday friday saturday sunday'.split()})]
    def write(changed):
        times=[]
        for n in range(100,121):
            for i,sid in enumerate(['A','B','C']):
                if changed and n==101 and sid=='B':continue
                minute=10*i+(10 if changed and n==100 else 0)
                times.append(dict(trip_id='t'+str(n),stop_sequence=str(i+1),stop_id=sid,departure_time=f'08:{minute:02d}:00',pickup_type='0'))
        for i,sid in enumerate(['A2','C']):times.append(dict(trip_id='platform2',stop_sequence=str(i+1),stop_id=sid,departure_time=f'08:{30+i*10:02d}:00',pickup_type='0'))
        tables={'agency.txt':[dict(agency_id='3',agency_name='אגד (ABC)',agency_url='https://example.org')],'routes.txt':routes,'trips.txt':trips,'stops.txt':stops,'calendar.txt':calendar,'stop_times.txt':times}
        with zipfile.ZipFile(zpath,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for name,rows in tables.items():
                s=io.StringIO();w=csv.DictWriter(s,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows);z.writestr(name,s.getvalue())
    state=root/'state.sqlite.gz';changes=root/'changes'
    write(False);run(zpath,state,changes,date(2026,11,13),'2026-11-13T12:00:00+02:00')
    write(True);run(zpath,state,changes,date(2026,11,13),'2026-11-13T13:00:00+02:00')
    site=root/'site';build(zpath,site,date(2026,11,13));shutil.copytree(changes,site/'data/changes')
    # Deterministic freshness timestamps matching the browser's frozen clock.
    for file in [site/'data/index.json',site/'data/station-search.json',*list((site/'data/stations').glob('*.json'))]:
        import json
        data=json.loads(file.read_text());data['updated']='2026-11-13T13:00:00+02:00';file.write_text(json.dumps(data,ensure_ascii=False))
    repository=Path(__file__).resolve().parents[1]
    for name in ['index.html','changes.html','aliases.js','packing.js','pdf.js','logo.svg','favicon.svg']:
        shutil.copy(repository/name,site/name)
    shutil.copy(repository/'scripts/shes.js',site/'shes.js')
    shutil.copytree(repository/'assets',site/'assets')
    return site

if __name__=='__main__':
    fixture(Path(sys.argv[1]))
