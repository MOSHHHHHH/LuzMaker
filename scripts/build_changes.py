#!/usr/bin/env python3
"""Compact per-station GTFS change detection. Standard-library only.

Snapshots are keyed by service date; comparisons are between publications of
the SAME service date, never between adjacent weekdays.
"""
import argparse
import csv
import hashlib
import io
import json
import zipfile
from zoneinfo import ZoneInfo
from datetime import datetime
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

def records(z, name):
    found = next((n for n in z.namelist() if n.rsplit("/", 1)[-1] == name), None)
    if not found:
        return []
    with z.open(found) as f:
        return list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig")))

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
        for tid,trip in trips.items():
            seq = sorted(times.get(tid,[]))
            if not seq: continue
            route = routes[trip["route_id"]]
            line = route.get("route_short_name","")
            agency = route.get("agency_id","")
            direction = trip.get("direction_id","")
            identity = "|".join((agency,line,direction))
            stop_ids = [s for _,s,_ in seq]
            route_hash = hashlib.sha256(json.dumps(stop_ids).encode()).hexdigest()[:16]
            for day,enabled in services.items():
                if trip.get("service_id") not in enabled: continue
                for _,sid,clock in seq:
                    if sid not in stops: continue
                    code,name = stops[sid]
                    entry = result[day][code][identity]
                    entry["routes"][route_hash] = [[stops[s][0],stops[s][1]] for s in stop_ids if s in stops]
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
    p=argparse.ArgumentParser()
    p.add_argument("--zip",type=Path,required=True)
    p.add_argument("--state",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--today",type=date.fromisoformat,default=datetime.now(ZoneInfo("Asia/Jerusalem")).date())
    p.add_argument("--end",type=date.fromisoformat,required=True)
    args=p.parse_args()
    start=args.today-timedelta(days=30)
    days=[start+timedelta(days=i) for i in range((args.end-start).days+1)]
    if not days: raise ValueError("GTFS horizon ends before rolling window")
    if len(days)>400: raise ValueError("Unreasonable GTFS horizon")
    fresh=snapshot(args.zip,days)
    previous=json.loads(args.state.read_text()) if args.state.exists() else {}
    changes=defaultdict(list)
    event_path=args.state.with_suffix(".events.json")
    saved_events=json.loads(event_path.read_text()) if event_path.exists() else {}
    for station,events in saved_events.items():
        for event in events:
            if start.isoformat() <= event["date"] <= args.end.isoformat():
                changes[station].append(event)
    observed_at=datetime.now(ZoneInfo("Asia/Jerusalem")).isoformat(timespec="seconds")
    for day in fresh:
        if day not in previous: continue  # First observation is not a change.
        for station,events in compare(previous,fresh,day).items():
            # Revisions supersede earlier observations for the same line and service day.
            for event in events:
                event["detectedAt"]=observed_at
                changes[station]=[e for e in changes[station] if not (e["date"]==day and e["line"]==event["line"])]
                changes[station].append(event)
    changes={station:sorted(events,key=lambda e:(e["date"],e["line"])) for station,events in changes.items() if events}
    event_path.parent.mkdir(parents=True,exist_ok=True)
    event_path.write_text(json.dumps(changes,ensure_ascii=False,separators=(",",":")))
    args.output.mkdir(parents=True,exist_ok=True)
    station_dir=args.output/"stations"
    station_dir.mkdir(exist_ok=True)
    for old_file in station_dir.glob("*.json"): old_file.unlink()
    for station,events in changes.items():
        (args.output/"stations"/(hashlib.sha256(station.encode()).hexdigest()[:20]+".json")).write_text(json.dumps({"station":station,"changes":events},ensure_ascii=False,separators=(",",":")))
    (args.output/"index.json").write_text(json.dumps({"start":start.isoformat(),"end":args.end.isoformat(),"stations":len(changes),"updated":observed_at},ensure_ascii=False))
    args.state.parent.mkdir(parents=True,exist_ok=True)
    args.state.write_text(json.dumps(fresh,ensure_ascii=False,separators=(",",":")))
if __name__=="__main__": main()
