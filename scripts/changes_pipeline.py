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
VERSION = 4

try:
    from .weekly_changes import describe, summary
except ImportError:
    from weekly_changes import describe, summary


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
    CREATE TABLE coverage(line TEXT,days TEXT,observed TEXT,PRIMARY KEY(line,observed));
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
            if old_meta.get('version') not in (3, VERSION):
                raise ValueError('Unsupported historical state schema; explicit migration required')
        raw, out = connect(tmp/'raw.db'), connect(tmp/'next.db')
        create_state(out)
        stats = build_raw(zip_path, raw, out, start, today)
        end = max(date.fromisoformat(stats['end']), date.fromisoformat(old_meta.get('end', stats['end'])))
        if old:
            for key in ('routes','stops','trips','stopTimes'):
                threshold = .8 if key in ('routes','stops') else .5
                if stats[key] < old_meta['stats'][key] * threshold and old_meta['stats'][key] - stats[key] > 100:
                    raise ValueError('Suspicious feed shrinkage: ' + key + '; keeping last valid publication')
            # Prior route definitions are needed to describe removed stops.
            out.executemany('INSERT OR IGNORE INTO routes VALUES(?,?)', old.execute('SELECT * FROM routes'))
        old_start = date.fromisoformat(old_meta.get('start', start.isoformat()))
        old_end = date.fromisoformat(old_meta.get('end', start.isoformat()))
        # Comparison coverage excludes absent dates beyond the feed's real horizon.
        fresh_shifts = {line:(lo,hi) for line,lo,hi in out.execute('SELECT * FROM line_shifts')}
        old_shifts = {line:(lo,hi) for line,lo,hi in old.execute('SELECT * FROM line_shifts')} if old else {}
        service_start, service_end = date.fromisoformat(stats['serviceStart']), date.fromisoformat(stats['serviceEnd'])
        old_service_start = date.fromisoformat(old_meta.get('stats', {}).get('serviceStart',stats['serviceStart']))
        old_service_end = date.fromisoformat(old_meta.get('stats', {}).get('serviceEnd',stats['serviceEnd']))
        def bounds(line, shifts, lo, hi):
            minimum,maximum = shifts.get(line,old_shifts.get(line,(0,0)))
            return lo + timedelta(days=max(0,maximum)), hi + timedelta(days=min(0,minimum))
        # Keep only complete transport dates. Partial edge dates cannot prove
        # additions/removals: they lack contributions from other service dates.
        allowed_by_line = {}
        for line in fresh_shifts.keys() | old_shifts.keys():
            # Removed overnight journeys still require neighbouring source
            # dates to prove absence at an edge. Use both shift ranges.
            a=fresh_shifts.get(line,old_shifts.get(line,(0,0)))
            b=old_shifts.get(line,a)
            union={line:(min(a[0],b[0]),max(a[1],b[1]))}
            lo,hi = bounds(line,union,service_start,service_end)
            lo,hi = max(start,lo),min(end,hi)
            allowed_by_line[line] = ((1 << ((hi-start).days+1))-1) ^ ((1 << ((lo-start).days))-1) if hi>=lo else 0
        # Coverage is independent of departures: a covered empty day is known
        # no-service; an uncovered day must never become a cancellation.
        coverage = {}
        old_coverage = defaultdict(dict)
        if old and old_meta.get('version') == VERSION:
            for line, mask, stamp in old.execute('SELECT * FROM coverage'):
                old_coverage[line][stamp] = int(mask,16)
        elif old:
            # Preserve v3 observations; seed coverage only for provable complete dates.
            for line in old_shifts:
                lo, hi = bounds(line,old_shifts,old_service_start,old_service_end)
                lo, hi = max(old_start,lo), min(old_end,hi)
                if hi >= lo:
                    old_coverage[line][old_meta['updated']] = ((1 << ((hi-old_start).days+1))-1) ^ ((1 << ((lo-old_start).days))-1)
        for line in allowed_by_line:
            fresh = allowed_by_line[line]
            records = {}
            for stamp, mask in old_coverage.get(line,{}).items():
                shift = (start-old_start).days
                mask = mask >> shift if shift >= 0 else mask << -shift
                mask &= ~fresh
                if mask:
                    records[stamp] = mask
            if fresh:
                records[observed] = records.get(observed,0) | fresh
            coverage[line] = records
            for stamp, mask in records.items():
                out.execute('INSERT INTO coverage VALUES(?,?,?)',(line,format(mask,'x'),stamp))
        def complete_profiles(current):
            return {line:{h:[v,mask & allowed_by_line[line]] for h,(v,mask) in values.items()
                          if mask & allowed_by_line[line]} for line,values in current.items()}
        visited = set()
        def consume(station, current):
            visited.add(station)
            current = complete_profiles(current)
            previous = load_station(old, station) if old else {}
            # Keep previous observations for EVERY date not fully covered by the
            # latest publication, including future dates beyond a shorter feed.
            for line, values in previous.items():
                for h,(value,mask) in values.items():
                    shift = (start-old_start).days
                    retained = (mask >> shift if shift >= 0 else mask << -shift) & ~allowed_by_line.get(line,0)
                    if retained:
                        target = current.setdefault(line,{})
                        if h in target:
                            target[h][1] |= retained
                        else:
                            target[h] = [value,retained]
            for line, values in current.items():
                for h, (value, mask) in values.items():
                    out.execute('INSERT OR IGNORE INTO profiles VALUES(?,?)', (h, pack(value)))
                    out.execute('INSERT INTO snapshots VALUES(?,?,?,?)', (station,line,h,format(mask,'x')))
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
        (stage/'details').mkdir()
        count = total = 0
        station_ids = [r[0] for r in out.execute('SELECT DISTINCT station FROM snapshots')]
        for station in station_ids:
            current = load_station(out,station)
            items, details, refs = [], {}, set()
            for line, values in current.items():
                records = coverage.get(line,{})
                covered = 0
                for mask in records.values():
                    covered |= mask
                pairs = covered & (covered << 7)
                while pairs:
                    bit = pairs & -pairs
                    idx = bit.bit_length()-1
                    pairs -= bit
                    ah,a = on_day(values,idx-7)
                    bh,b = on_day(values,idx)
                    if ah == bh:
                        continue
                    day = start + timedelta(days=idx)
                    schedule, route, tags = describe(a,b)
                    before_routes, after_routes = (a or {}).get('routes',[]), (b or {}).get('routes',[])
                    def sequences(ids):
                        return [json.loads(out.execute('SELECT data FROM routes WHERE id=?',(h,)).fetchone()[0]) for h in ids]
                    old_routes,new_routes = sequences(before_routes),sequences(after_routes)
                    old_stops = {s[0]:s[1] for seq in old_routes for s in seq}
                    new_stops = {s[0]:s[1] for seq in new_routes for s in seq}
                    added = sorted(new_stops.keys()-old_stops.keys())
                    removed = [[k,old_stops[k]] for k in sorted(old_stops.keys()-new_stops.keys())]
                    if route:
                        if added: tags.append('נוספו תחנות במסלול')
                        if removed: tags.append('הוסרו תחנות מהמסלול')
                        if not added and not removed: tags.append('השתנה סדר התחנות במסלול')
                    def stamp(day_idx):
                        return next(t for t,m in records.items() if m & (1 << day_idx))
                    item = dict(id=digest([station,line,day.isoformat(),ah,bh]),date=day.isoformat(),
                                comparisonDate=(day-timedelta(days=7)).isoformat(),line=line,
                                type='added' if a is None else 'removed' if b is None else 'route_changed' if route else 'schedule_changed',
                                scheduleChanged=schedule,routeChanged=route,tags=tags,
                                before=summary(a),after=summary(b),beforeProfile=ah,afterProfile=bh,
                                beforeRoutes=before_routes,routes=after_routes,addedStops=added,removedStops=removed,
                                beforePublication=stamp(idx-7),afterPublication=stamp(idx),detectedAt=observed)
                    path = new_routes or old_routes
                    item['routeLabel'] = path[0][0][1]+' ← '+path[0][-1][1] if path else ''
                    for h,profile in [(ah,a),(bh,b)]:
                        if h: details[h] = profile
                    refs.update(before_routes+after_routes)
                    items.append(item)
                    out.execute('INSERT INTO events VALUES(?,?,?,?)',(station,day.isoformat(),line,pack(item)))
            definitions = {h:json.loads(out.execute('SELECT data FROM routes WHERE id=?',(h,)).fetchone()[0]) for h in refs}
            data = dict(station=station,changes=items,comparison='weekly',coverageAvailable=any(coverage.get(line) for line in current))
            name = hashlib.sha256(station.encode()).hexdigest()[:20]+'.json'
            (stage/'stations'/name).write_text(pack(data),encoding='utf-8')
            (stage/'details'/name).write_text(pack(dict(station=station,profiles=details,routeDefinitions=definitions)),encoding='utf-8')
            count += 1
            total += len(items)
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
        coverage_start = (start + timedelta(days=(observed_mask & -observed_mask).bit_length()-1)).isoformat()
        metadata = dict(comparison='weekly',archiveSnapshots=sources, version=VERSION,start=start.isoformat(),end=end.isoformat(),
                        firstCovered=coverage_start,updated=observed,stations=count,
                        baselineObservedAt=old_meta.get('baselineObservedAt',observed),
                        historyStart=coverage_start,
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
