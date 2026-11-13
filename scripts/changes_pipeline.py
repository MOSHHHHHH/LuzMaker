"""Disk-backed nationwide change detector. No runtime database is published.

Each station/variant profile is stored once with a bitmask of transport dates.
Stop sequences are content addressed by public stop codes. SQLite is a temporary
external sorter; the durable state is a gzip-compressed SQLite database.
"""
import argparse
import csv
import gzip
import hashlib
import io
import itertools
import json
import os
import resource
import shutil
import sqlite3
import tempfile
import time
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

SOURCE = 'https://gtfs.mot.gov.il/gtfsfiles/israel-public-transportation.zip'
WEEK = 'monday tuesday wednesday thursday friday saturday sunday'.split()
VERSION = 3


def pack(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True)


def digest(value):
    return hashlib.sha256(pack(value).encode()).hexdigest()[:24]


def rows(z, name, required=False):
    names = [n for n in z.namelist() if n.rsplit('/', 1)[-1] == name]
    if len(names) > 1 or (required and not names):
        raise ValueError('Missing or ambiguous GTFS table: ' + name)
    if names:
        with z.open(names[0]) as f:
            yield from csv.DictReader(io.TextIOWrapper(f, encoding='utf-8-sig', newline=''))


def ymd(raw):
    return datetime.strptime(raw, '%Y%m%d').date()


def previous_month(day):
    last = day.replace(day=1) - timedelta(days=1)
    return last.replace(day=min(day.day, last.day))


def clock(raw):
    h, m, s = map(int, raw.split(':'))
    if h < 0 or not 0 <= m < 60 or not 0 <= s < 60:
        raise ValueError('Invalid GTFS time')
    return h * 3600 + m * 60 + s


def calendars(z, referenced, start):
    """Enumerate actual active dates, including exception-only service calendars."""
    active = defaultdict(set)
    for r in rows(z, 'calendar.txt'):
        if r['service_id'] not in referenced:
            continue
        lo, hi = ymd(r['start_date']), ymd(r['end_date'])
        if hi < lo:
            raise ValueError('Inverted calendar')
        day = max(lo, start - timedelta(days=7))
        while day <= hi:
            if r[WEEK[day.weekday()]] == '1':
                active[r['service_id']].add(day)
            day += timedelta(days=1)
    for r in rows(z, 'calendar_dates.txt'):
        if r['service_id'] not in referenced:
            continue
        day = ymd(r['date'])
        if r['exception_type'] == '1':
            if day >= start - timedelta(days=7):
                active[r['service_id']].add(day)
        elif r['exception_type'] == '2':
            active[r['service_id']].discard(day)
        else:
            raise ValueError('Invalid calendar exception')
    dates = set().union(*active.values()) if active else set()
    if not dates:
        raise ValueError('No active services')
    return active, min(dates), max(dates)


def connect(path):
    db = sqlite3.connect(path)
    db.execute('PRAGMA journal_mode=OFF')  # scratch files only; published state replaced atomically
    db.execute('PRAGMA synchronous=OFF')
    db.execute('PRAGMA cache_size=-32768')
    db.execute('PRAGMA temp_store=FILE')
    return db


def create_state(db):
    db.executescript('''
    CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);
    CREATE TABLE routes(id TEXT PRIMARY KEY,data TEXT);
    CREATE TABLE profiles(id TEXT PRIMARY KEY,data TEXT);
    CREATE TABLE line_shifts(line TEXT PRIMARY KEY,lo INTEGER,hi INTEGER);
    CREATE TABLE snapshots(station TEXT,line TEXT,profile TEXT,days TEXT,
      PRIMARY KEY(station,line,profile));
    CREATE TABLE events(station TEXT,day TEXT,line TEXT,data TEXT,
      PRIMARY KEY(station,day,line));
    ''')


def meta(db):
    return {k: json.loads(v) for k, v in db.execute('SELECT key,value FROM meta')}


def build_raw(zip_path, db, out, start, today):
    db.executescript('''CREATE TABLE times(trip TEXT,seq INTEGER,stop TEXT,t INTEGER,pickup INTEGER);
      CREATE TABLE departures(station TEXT,line TEXT,route TEXT,t INTEGER,mask TEXT);''')
    with zipfile.ZipFile(zip_path) as z:
        if next(rows(z, 'frequencies.txt'), None) is not None:
            raise ValueError('Frequency-based GTFS requires expansion; keeping previous valid state')
        # All supported public transport modes, not only buses.
        routes = {r['route_id']: r for r in rows(z, 'routes.txt', True)}
        agencies = {r['agency_id']: r.get('agency_name', r['agency_id']) for r in rows(z, 'agency.txt', True)}
        stops = {r['stop_id']: [r.get('stop_code') or r['stop_id'], r.get('stop_name', '')]
                 for r in rows(z, 'stops.txt', True)}
        trips = {}
        for r in rows(z, 'trips.txt', True):
            route = routes[r['route_id']]
            # Israeli route_desc is the official line/direction/alternative code.
            # It survives route_id and trip_id churn. Do not key by stop sequence:
            # that would turn a route edit into unrelated added/removed services.
            desc = route.get('route_desc', '')
            identity = [route.get('agency_id', ''), route.get('route_short_name', ''),
                        r.get('direction_id', ''), desc or r.get('trip_headsign', '')]
            trips[r['trip_id']] = (r['service_id'], pack(identity))
        if not routes or not stops or not trips or not agencies:
            raise ValueError('Empty GTFS input')
        active, lo, hi = calendars(z, {v[0] for v in trips.values()}, start)
        if hi < today:
            raise ValueError('Stale feed: no current/future service')
        batch = []
        count = 0
        for r in rows(z, 'stop_times.txt', True):
            if r['trip_id'] not in trips or r['stop_id'] not in stops:
                raise ValueError('Dangling trip/stop reference')
            t = clock(r.get('departure_time') or r.get('arrival_time') or '')
            if t > 7 * 86400:
                raise ValueError('Trip exceeds supported seven-day duration; inspect feed')
            batch.append((r['trip_id'], int(r['stop_sequence']), r['stop_id'], t, int(r.get('pickup_type') or 0)))
            count += 1
            if len(batch) == 20000:
                db.executemany('INSERT INTO times VALUES(?,?,?,?,?)', batch)
                batch.clear()
        db.executemany('INSERT INTO times VALUES(?,?,?,?,?)', batch)
        db.commit()
        print('Imported', count, 'stop times', flush=True)
        db.execute('CREATE INDEX time_trip ON times(trip,seq)')
        seen = set()
        batch = []
        latest = hi
        earliest = lo
        line_shifts = {}
        for tid, group in itertools.groupby(db.execute('SELECT trip,seq,stop,t,pickup FROM times ORDER BY trip,seq'), lambda x: x[0]):
            seq = list(group)
            if len(seq) < 2 or len({r[1] for r in seq}) != len(seq):
                raise ValueError('Incomplete or duplicated trip stop sequence: ' + tid)
            seen.add(tid)
            service, line = trips[tid]
            public_seq = [stops[r[2]] for r in seq]
            route_hash = digest([s[0] for s in public_seq])
            out.execute('INSERT OR IGNORE INTO routes VALUES(?,?)', (route_hash, pack(public_seq)))
            for _, _, sid, t, pickup in seq:
                if pickup == 1:
                    continue
                shift = (t - 10800) // 86400
                bounds = line_shifts.setdefault(line, [shift, shift])
                bounds[0] = min(bounds[0], shift)
                bounds[1] = max(bounds[1], shift)
                mask = 0
                for service_day in active[service]:
                    day = service_day + timedelta(days=shift)
                    if day >= start:
                        latest = max(latest, day)
                        earliest = min(earliest, day)
                        mask |= 1 << (day - start).days
                if mask:
                    batch.append((stops[sid][0], line, route_hash, t - shift * 86400, format(mask, 'x')))
                if len(batch) >= 20000:
                    db.executemany('INSERT INTO departures VALUES(?,?,?,?,?)', batch)
                    batch.clear()
        db.executemany('INSERT INTO departures VALUES(?,?,?,?,?)', batch)
        if seen != set(trips):
            raise ValueError('Trips missing stop times')
        out.executemany('INSERT INTO line_shifts VALUES(?,?,?)', [(line,*bounds) for line,bounds in line_shifts.items()])
        db.commit()
        db.execute('DROP TABLE times')
        db.execute('CREATE INDEX dep_station ON departures(station,line)')
        return dict(routes=len(routes), stops=len(stops), trips=len(trips), stopTimes=count,
                    sourceServiceDates=len({d for dates in active.values() for d in dates if d >= start}),
                    serviceStart=lo.isoformat(), serviceEnd=hi.isoformat(),
                    end=latest.isoformat(), firstCovered=max(start, earliest).isoformat(), agencies=agencies)


def station_profiles(db, start, end):
    for station, station_rows in itertools.groupby(db.execute('SELECT station,line,route,t,mask FROM departures ORDER BY station,line'), lambda x: x[0]):
        profiles = {}
        for line, line_rows in itertools.groupby(station_rows, lambda x: x[1]):
            dates = defaultdict(lambda: {'routes': set(), 'departures': []})
            for _, _, route, t, raw_mask in line_rows:
                mask = int(raw_mask, 16)
                while mask:
                    bit = mask & -mask
                    idx = bit.bit_length() - 1
                    dates[idx]['routes'].add(route)
                    dates[idx]['departures'].append(t)
                    mask -= bit
            values = {}
            for idx, value in dates.items():
                value = {'routes': sorted(value['routes']), 'departures': sorted(value['departures'])}
                h = digest(value)
                if h not in values:
                    values[h] = [value, 0]
                values[h][1] |= 1 << idx
            profiles[line] = values
        yield station, profiles


def load_station(db, station):
    values = defaultdict(dict)
    for line, h, mask, raw in db.execute('SELECT s.line,s.profile,s.days,p.data FROM snapshots s JOIN profiles p ON s.profile=p.id WHERE s.station=?', (station,)):
        values[line][h] = [json.loads(raw), int(mask, 16)]
    return values


def on_day(values, idx):
    return next(((h, p) for h, (p, mask) in values.items() if mask & (1 << idx)), (None, None)) if idx >= 0 else (None, None)


def event(before, after, day, line, observed, station, old_event, out):
    ah, a = before
    bh, b = after
    kind = 'added' if a is None else 'removed' if b is None else 'route_changed' if a['routes'] != b['routes'] else 'schedule_changed'
    item = dict(date=day, line=line, type=kind, detectedAt=observed,
                id=digest([station, day, line, ah, bh, old_event.get('id')]),
                revision=old_event.get('revision', 0) + 1)
    if old_event:
        item['supersedes'] = old_event['id']
    for key, profile in [('before', a), ('after', b)]:
        times = profile['departures'] if profile else []
        gaps = [y-x for x,y in zip(times,times[1:])]
        item[key] = dict(count=len(times), first=times[0] if times else None,
                         last=times[-1] if times else None,
                         meanInterval=round(sum(gaps)/len(gaps)) if gaps else None)
    if kind in ('route_changed', 'added', 'removed'):
        def sequences(profile):
            return [json.loads(out.execute('SELECT data FROM routes WHERE id=?', (h,)).fetchone()[0]) for h in profile['routes']] if profile else []
        old_routes, new_routes = sequences(a), sequences(b)
        old_stops = {s[0]: s[1] for seq in old_routes for s in seq}
        new_stops = {s[0]: s[1] for seq in new_routes for s in seq}
        item.update(routes=b['routes'] if b else [], addedStops=sorted(new_stops.keys()-old_stops.keys()),
                    removedStops=[[k,old_stops[k]] for k in sorted(old_stops.keys()-new_stops.keys())])
    return item


def run(zip_path, state, output, today, observed=None, provenance=None):
    started = time.monotonic()
    observed = observed or datetime.now(ZoneInfo('Asia/Jerusalem')).isoformat(timespec='seconds')
    start = previous_month(today)
    state, output = Path(state), Path(output)
    state.parent.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='changes-', dir=state.parent) as tmp:
        tmp = Path(tmp)
        old = None
        old_meta = {}
        if state.exists():
            with gzip.open(state, 'rb') as src, (tmp/'previous.db').open('wb') as dst:
                shutil.copyfileobj(src, dst)
            old = connect(tmp/'previous.db')
            if old.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Corrupt historical state')
            old_meta = meta(old)
            if old_meta.get('version') != VERSION:
                raise ValueError('Unsupported historical state schema; explicit migration required')
        raw, out = connect(tmp/'raw.db'), connect(tmp/'next.db')
        create_state(out)
        stats = build_raw(zip_path, raw, out, start, today)
        end = date.fromisoformat(stats['end'])
        if old:
            for key in ('routes','stops','trips','stopTimes'):
                threshold = .8 if key in ('routes','stops') else .5
                if stats[key] < old_meta['stats'][key] * threshold and old_meta['stats'][key] - stats[key] > 100:
                    raise ValueError('Suspicious feed shrinkage: ' + key + '; keeping last valid publication')
            # Prior route definitions are needed to describe removed stops.
            out.executemany('INSERT OR IGNORE INTO routes VALUES(?,?)', old.execute('SELECT * FROM routes'))
            for station, day, line, data in old.execute('SELECT * FROM events WHERE day>=? AND day<=?', (start.isoformat(), end.isoformat())):
                out.execute('INSERT INTO events VALUES(?,?,?,?)', (station, day, line, data))
        old_start = date.fromisoformat(old_meta.get('start', start.isoformat()))
        old_end = date.fromisoformat(old_meta.get('end', start.isoformat()))
        # Comparison coverage excludes absent dates beyond the feed's real horizon.
        first = date.fromisoformat(stats['firstCovered'])
        fresh_shifts = {line:(lo,hi) for line,lo,hi in out.execute('SELECT * FROM line_shifts')}
        old_shifts = {line:(lo,hi) for line,lo,hi in old.execute('SELECT * FROM line_shifts')} if old else {}
        service_start, service_end = date.fromisoformat(stats['serviceStart']), date.fromisoformat(stats['serviceEnd'])
        old_service_start = date.fromisoformat(old_meta.get('stats', {}).get('serviceStart',stats['serviceStart']))
        old_service_end = date.fromisoformat(old_meta.get('stats', {}).get('serviceEnd',stats['serviceEnd']))
        def bounds(line, shifts, lo, hi):
            minimum,maximum = shifts.get(line,(0,0))
            return lo + timedelta(days=max(0,maximum)), hi + timedelta(days=min(0,minimum))
        # Keep only complete transport dates. Partial edge dates cannot prove
        # additions/removals: they lack contributions from other service dates.
        allowed_by_line = {}
        comparison_ranges = {}
        for line in fresh_shifts.keys() | old_shifts.keys():
            lo,hi = bounds(line,fresh_shifts,service_start,service_end)
            lo,hi = max(start,lo),min(end,hi)
            allowed_by_line[line] = ((1 << ((hi-start).days+1))-1) ^ ((1 << ((lo-start).days))-1) if hi>=lo else 0
            a = fresh_shifts.get(line,old_shifts.get(line,(0,0)))
            b = old_shifts.get(line,fresh_shifts.get(line,(0,0)))
            union = {line:(min(a[0],b[0]),max(a[1],b[1]))}
            new_lo,new_hi = bounds(line,union,service_start,service_end)
            old_lo,old_hi = bounds(line,union,old_service_start,old_service_end)
            comparison_ranges[line] = (max(start,new_lo,old_lo),min(end,old_end,new_hi,old_hi))
        def complete_profiles(current):
            return {line:{h:[v,mask & allowed_by_line[line]] for h,(v,mask) in values.items()
                          if mask & allowed_by_line[line]} for line,values in current.items()}
        total = 0
        visited = set()
        def consume(station, current):
            nonlocal total
            visited.add(station)
            current = complete_profiles(current)
            previous = load_station(old, station) if old else {}
            for line, values in current.items():
                for h, (value, mask) in values.items():
                    out.execute('INSERT OR IGNORE INTO profiles VALUES(?,?)', (h, pack(value)))
                    out.execute('INSERT INTO snapshots VALUES(?,?,?,?)', (station, line, h, format(mask,'x')))
            if not old:
                return
            for line in previous.keys() | current.keys():
                day,comparison_end = comparison_ranges[line]
                while day <= comparison_end:
                    a = on_day(previous.get(line, {}), (day-old_start).days)
                    b = on_day(current.get(line, {}), (day-start).days)
                    if a[0] != b[0]:
                        prior = out.execute('SELECT data FROM events WHERE station=? AND day=? AND line=?', (station, day.isoformat(), line)).fetchone()
                        item = event(a,b,day.isoformat(),line,observed,station,json.loads(prior[0]) if prior else {},out)
                        out.execute('INSERT OR REPLACE INTO events VALUES(?,?,?,?)', (station,day.isoformat(),line,pack(item)))
                        total += 1
                    day += timedelta(days=1)
            # Preserve observations from historical dates no longer included by the
            # current publisher. They are evidence, not cancellations.
            for line, values in previous.items():
                for h,(value,mask) in values.items():
                    retained = 0
                    while mask:
                        bit = mask & -mask
                        day = old_start + timedelta(days=bit.bit_length()-1)
                        new_lo,_ = bounds(line,fresh_shifts,service_start,service_end)
                        if start <= day < new_lo:
                            retained |= 1 << (day-start).days
                        mask -= bit
                    if retained:
                        out.execute('INSERT OR IGNORE INTO profiles VALUES(?,?)', (h,pack(value)))
                        row = out.execute('SELECT days FROM snapshots WHERE station=? AND line=? AND profile=?',(station,line,h)).fetchone()
                        retained |= int(row[0],16) if row else 0
                        out.execute('INSERT OR REPLACE INTO snapshots VALUES(?,?,?,?)',(station,line,h,format(retained,'x')))
        for station, current in station_profiles(raw, start, end):
            consume(station, current)
            if len(visited) % 5000 == 0:
                print('Processed', len(visited), 'stations', flush=True)
        if old:
            for (station,) in old.execute('SELECT DISTINCT station FROM snapshots'):
                if station not in visited:
                    consume(station,{})
        if not out.execute('SELECT 1 FROM snapshots LIMIT 1').fetchone():
            raise ValueError('Empty generated snapshot')
        if old:
            out.executemany('INSERT OR IGNORE INTO line_shifts VALUES(?,?,?)', old.execute('SELECT * FROM line_shifts'))
        profile_count = out.execute('SELECT count(*) FROM snapshots').fetchone()[0]
        if old and profile_count < old_meta['stats']['stationProfiles'] * .5 and old_meta['stats']['stationProfiles'] - profile_count > 100:
            raise ValueError('Suspicious loss of active profiles; preserving previous dataset')
        stage = tmp/'published'
        (stage/'stations').mkdir(parents=True)
        count = 0
        for station, events in itertools.groupby(out.execute('SELECT station,data FROM events ORDER BY station,day,line'),lambda r:r[0]):
            items = [json.loads(r[1]) for r in events]
            refs = {h for item in items for h in item.get('routes', [])}
            definitions = {h: json.loads(out.execute('SELECT data FROM routes WHERE id=?', (h,)).fetchone()[0]) for h in refs}
            data = {'station': station, 'changes': items, 'routeDefinitions': definitions}
            name = hashlib.sha256(station.encode()).hexdigest()[:20]+'.json'
            (stage/'stations'/name).write_text(pack(data),encoding='utf-8')
            count += 1
        observed_mask = 0
        for (mask,) in out.execute('SELECT days FROM snapshots'):
            observed_mask |= int(mask,16)
        stats.update(windowDates=(end-start).days+1, processedDates=observed_mask.bit_count(), changesThisRun=total,
                     events=out.execute('SELECT count(*) FROM events').fetchone()[0],
                     stationProfiles=out.execute('SELECT count(*) FROM snapshots').fetchone()[0],
                     stationsProcessed=len(visited))
        sources = old_meta.get('archiveSnapshots', [])
        if provenance and provenance not in sources:
            sources.append(provenance)
        metadata = dict(archiveSnapshots=sources, version=VERSION,start=start.isoformat(),end=end.isoformat(),
                        firstCovered=stats['firstCovered'],updated=observed,stations=count,
                        baselineObservedAt=old_meta.get('baselineObservedAt',observed),
                        historyStart=max(start.isoformat(), old_meta.get('historyStart',stats['firstCovered'])),
                        source=SOURCE,stats=stats)
        out.executemany('INSERT INTO meta VALUES(?,?)',[(k,pack(v)) for k,v in metadata.items()])
        out.commit()
        # Remove unused route definitions before persisting the next compact state.
        used = set()
        for (raw_profile,) in out.execute('SELECT data FROM profiles'):
            used.update(json.loads(raw_profile)['routes'])
        for (raw_event,) in out.execute('SELECT data FROM events'):
            used.update(json.loads(raw_event).get('routes', []))
        out.executemany('DELETE FROM routes WHERE id=?',[(h,) for (h,) in out.execute('SELECT id FROM routes') if h not in used])
        out.commit()
        out.execute('VACUUM')
        out.close()
        raw.close()
        if old:
            old.close()
        with (tmp/'next.db').open('rb') as src, gzip.open(tmp/'state.gz','wb',compresslevel=6) as dst:
            shutil.copyfileobj(src,dst)
        stats.update(snapshotBytes=(tmp/'state.gz').stat().st_size,
                     publishedBytes=sum(p.stat().st_size for p in stage.rglob('*.json')),
                     elapsedSeconds=round(time.monotonic()-started,2),
                     peakMemoryMiB=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,1))
        # Include the index itself in the published byte count (fixed point).
        station_bytes = stats['publishedBytes']
        for _ in range(5):
            stats['publishedBytes'] = station_bytes + len(pack(metadata).encode())
        (stage/'index.json').write_text(pack(metadata),encoding='utf-8')
        # Workflow publishes the complete state + data in one normal Git commit.
        # Local promotion is recoverable: keep the prior state until data is ready.
        backup = output.with_name(output.name+'.previous')
        if backup.exists():
            shutil.rmtree(backup)
        if output.exists():
            output.rename(backup)
        shutil.move(str(stage),output)
        os.replace(tmp/'state.gz',state)
        if backup.exists():
            shutil.rmtree(backup)
        print(pack(metadata),flush=True)
        return metadata


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zip',required=True,type=Path)
    parser.add_argument('--state',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--today',type=date.fromisoformat,default=datetime.now(ZoneInfo('Asia/Jerusalem')).date())
    args=parser.parse_args()
    run(args.zip,args.state,args.output,args.today)

if __name__=='__main__':
    main()
