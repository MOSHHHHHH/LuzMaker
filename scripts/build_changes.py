#!/usr/bin/env python3
"""Station detector CLI and backward-compatible small-fixture comparison helpers.

Nationwide builds use changes_pipeline.py and compressed SQLite state. The
legacy snapshot/compare helpers below are only for small in-memory fixtures.

Snapshots are keyed by service date; comparisons are between publications of
the SAME service date, never between adjacent weekdays.
"""
import csv
import hashlib
import io
import json
import zipfile
from collections import defaultdict

def records(z, name):
    found = next((n for n in z.namelist() if n.rsplit("/", 1)[-1] == name), None)
    if not found:
        return []
    with z.open(found) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))

def active_services(z, days):
    masks = defaultdict(set)
    valid_days = {d.isoformat() for d in days}
    weekdays = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
    for row in records(z,"calendar.txt"):
        for d in days:
            if row["start_date"] <= d.strftime("%Y%m%d") <= row["end_date"] and row.get(weekdays[d.weekday()]) == "1":
                masks[d.isoformat()].add(row["service_id"])
    for row in records(z,"calendar_dates.txt"):
        day = row["date"]
        try: key = date(int(day[:4]),int(day[4:6]),int(day[6:8])).isoformat()
        except ValueError: continue
        if key not in valid_days: continue
        if row["exception_type"] == "1": masks[key].add(row["service_id"])
        if row["exception_type"] == "2": masks[key].discard(row["service_id"])
    return masks

def snapshot(zip_path, days):
    with zipfile.ZipFile(zip_path) as z:
        services = active_services(z, days)
        routes = {r["route_id"]: r for r in records(z,"routes.txt") if r.get("route_type") == "3"}
        stops = {r["stop_id"]: [r.get("stop_code") or r["stop_id"],r.get("stop_name","")] for r in records(z,"stops.txt")}
        trips = {r["trip_id"]:r for r in records(z,"trips.txt") if r.get("route_id") in routes}
        times = defaultdict(list)
        for r in records(z,"stop_times.txt"):
            if r.get("trip_id") in trips:
                times[r["trip_id"]].append((int(r["stop_sequence"]),r["stop_id"],r.get("departure_time") or r.get("arrival_time") or ""))
        result = {d.isoformat():defaultdict(lambda:defaultdict(lambda:{"routes":{}, "departures":[]})) for d in days}
        services_by_id = defaultdict(list)
        for service_day,enabled in services.items():
            for service_id in enabled:
                services_by_id[service_id].append(service_day)
        for tid,trip in trips.items():
            seq = sorted(times.get(tid,[]))
            if not seq: continue
            route = routes[trip["route_id"]]
            line = route.get("route_short_name","")
            agency = route.get("agency_id","")
            direction = trip.get("direction_id","")
            identity = "|".join((agency,line,direction))
            stop_ids = [s for _,s,_ in seq]
            route_stops = [[stops[s][0],stops[s][1]] for s in stop_ids if s in stops]
            route_hash = hashlib.sha256(json.dumps([stops[s][0] for s in stop_ids]).encode()).hexdigest()[:16]
            for day in services_by_id.get(trip.get("service_id"), ()):
                for _,sid,clock in seq:
                    if sid not in stops: continue
                    code,name = stops[sid]
                    entry = result[day][code][identity]
                    entry["routes"][route_hash] = route_stops
                    entry["departures"].append(clock)
        return {day:{station:{line:{"routes":v["routes"],"departures":sorted(v["departures"])} for line,v in lines.items()} for station,lines in stations.items()} for day,stations in result.items()}

def compare(previous, current, day):
    changes=defaultdict(list)
    old=previous.get(day,{})
    new=current.get(day,{})
    for station in set(old)|set(new):
        before=old.get(station,{})
        after=new.get(station,{})
        for line in sorted(set(before)|set(after)):
            a,b=before.get(line),after.get(line)
            if not a: kind="added"
            elif not b: kind="removed"
            elif set(a["routes"]) != set(b["routes"]): kind="route_changed"
            elif a["departures"] != b["departures"]: kind="schedule_changed"
            else: continue
            item={"date":day,"line":line,"type":kind}
            if kind=="route_changed":
                old_routes=list(a["routes"].values())
                new_routes=list(b["routes"].values())
                old_codes={s[0] for route in old_routes for s in route}
                new_codes={s[0] for route in new_routes for s in route}
                item["routes"]=new_routes
                item["addedStops"]=sorted(new_codes-old_codes)
                item["removedStops"]=sorted(old_codes-new_codes)
            changes[station].append(item)
    return changes

def main():
    # Retain the small-fixture comparison API; nationwide CLI uses disk-backed state.
    try:
        from scripts.changes_pipeline import main as pipeline_main
    except ModuleNotFoundError:
        from changes_pipeline import main as pipeline_main
    pipeline_main()

if __name__ == "__main__":
    main()
