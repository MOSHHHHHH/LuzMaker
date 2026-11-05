#!/usr/bin/env python3
"""Build compact, date-aware bus schedules for LZM Maker from the official Israeli GTFS ZIP.

The displayed transport day is 03:00 through 02:59:59 the following calendar day.
Output clock minutes run from 180 (03:00) through 1619 (02:59 next day).
A 14-bit mask represents the next 14 transport days, beginning on index.start.
No external Python dependencies are required.
"""
import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import sys
import time
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

URL = "https://gtfs.mot.gov.il/gtfsfiles/israel-public-transportation.zip"
DAYS = 14
OFFSET = 3
ALL_DAYS = (1 << DAYS) - 1


def rows(zf, filename):
    matches = [name for name in zf.namelist() if name.rsplit("/", 1)[-1].lower() == filename.lower()]
    if not matches:
        if filename == "calendar.txt":
            return iter(())
        if filename == "calendar_dates.txt":
            return iter(())
        raise ValueError("GTFS missing required file: " + filename)

    def read():
        with zf.open(matches[0]) as raw:
            with io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="") as src:
                yield from csv.DictReader(src)
    return read()


def ymd(raw):
    return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))


def minute(raw):
    hh, mm, *_ = raw.split(":")
    return int(hh) * 60 + int(mm)


def download(dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(4):
        try:
            req = urllib.request.Request(URL, headers={"User-Agent": "LZM-Maker-GTFS/1.0"})
            with urllib.request.urlopen(req, timeout=100) as r, open(str(dest) + ".tmp", "wb") as f:
                shutil.copyfileobj(r, f, 1024 * 1024)
            os.replace(str(dest) + ".tmp", dest)
            print("Downloaded", dest.stat().st_size, "bytes", flush=True)
            return
        except Exception as e:
            print("Download error", repr(e), flush=True)
            if attempt == 3:
                raise
            time.sleep(min(2 ** (attempt + 2), 30))


def build(zip_path, out, start):
    dates = [start + timedelta(days=i - OFFSET) for i in range(DAYS + 2 * OFFSET)]
    known_dates = [d.strftime("%Y%m%d") for d in dates]
    output_tmp = out.with_name(out.name + "_building")
    if output_tmp.exists():
        shutil.rmtree(output_tmp)
    (output_tmp / "data" / "lines").mkdir(parents=True)

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        print("ZIP entries:", len(names), flush=True)
        agencies = {r.get("agency_id", ""): r.get("agency_name", "") for r in rows(zf, "agency.txt")}
        routes = {}
        by_line = defaultdict(set)
        for r in rows(zf, "routes.txt"):
            if r.get("route_type") != "3":
                continue
            rid = r["route_id"]
            number = r.get("route_short_name", "").strip()
            if not number:
                continue
            routes[rid] = (number, r.get("route_long_name", "").strip(), agencies.get(r.get("agency_id", ""), ""), r.get("agency_id", ""), r.get("route_desc", ""))
            by_line[number].add(rid)
        if not routes:
            raise ValueError("No bus routes found")
        print("Bus routes:", len(routes), "line numbers:", len(by_line), flush=True)

        service_masks = defaultdict(int)
        weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        for r in rows(zf, "calendar.txt"):
            try:
                lo, hi = ymd(r["start_date"]), ymd(r["end_date"])
            except (KeyError, ValueError):
                continue
            for i, d in enumerate(dates):
                if lo <= d <= hi and r.get(weekdays[d.weekday()], "0") == "1":
                    service_masks[r["service_id"]] |= 1 << i
        # Exceptions override weekly rules. calendar_dates may be the sole source.
        date_indices = {raw: i for i, raw in enumerate(known_dates)}
        for r in rows(zf, "calendar_dates.txt"):
            idx = date_indices.get(r.get("date", ""))
            if idx is None:
                continue
            bit = 1 << idx
            if r.get("exception_type") == "1":
                service_masks[r["service_id"]] |= bit
            elif r.get("exception_type") == "2":
                service_masks[r["service_id"]] &= ~bit
        if not any(service_masks.values()):
            raise ValueError("No active GTFS services in requested period")
        print("Active services:", sum(bool(v) for v in service_masks.values()), flush=True)

        # Variants are split by route and direction to avoid mixing opposite journeys.
        trip_index = {}
        variants = {}
        for r in rows(zf, "trips.txt"):
            rid = r.get("route_id")
            if rid not in routes:
                continue
            mask = service_masks.get(r.get("service_id", ""), 0)
            if not mask:
                continue
            direction = r.get("direction_id", "")
            key = (rid, direction)
            if key not in variants:
                number, long_name, agency, agency_id, route_desc = routes[rid]
                identity = "\x1f".join((rid, direction))
                identifier = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]
                title = long_name or r.get("trip_headsign", "") or number
                parts = route_desc.rsplit("-", 2)
                alternative = parts[-1] if len(parts) == 3 else ""
                if direction:
                    title += " · כיוון " + direction
                variants[key] = {
                    "id": identifier, "name": title, "agency": agency,
                    "alternative": alternative, "route_desc": route_desc,
                    "line": number,
                    "stops": {}, "t": defaultdict(lambda: defaultdict(list))
                }
            trip_index[r["trip_id"]] = (key, mask)
        if not trip_index:
            raise ValueError("No matching trips in GTFS")
        print("Active trips:", len(trip_index), "route variants:", len(variants), flush=True)

        # Collect only stops actually present in trips within this publication window.
        stop_meta = {}
        for r in rows(zf, "stops.txt"):
            stop_meta[r["stop_id"]] = (r.get("stop_code") or r["stop_id"], r.get("stop_name", "תחנה לא ידועה"))
        processed = 0
        for r in rows(zf, "stop_times.txt"):
            info = trip_index.get(r.get("trip_id"))
            if not info or r.get("pickup_type") == "1":
                continue
            raw_time = r.get("arrival_time") or r.get("departure_time")
            if not raw_time:
                continue
            try:
                m = minute(raw_time)
                seq = int(r.get("stop_sequence", "0"))
            except ValueError:
                continue
            # Map a GTFS service date to a transport day (03:00..next 02:59).
            shift = (m - 180) // 1440
            normalized_minute = m - shift * 1440
            key, service_mask = info
            mask = ((service_mask << shift) if shift >= 0 else (service_mask >> -shift)) >> OFFSET & ALL_DAYS
            if not mask:
                continue
            variant = variants[key]
            stop_id = r["stop_id"]
            if stop_id not in stop_meta:
                continue
            old = variant["stops"].get(stop_id)
            if old is None or seq < old:
                variant["stops"][stop_id] = seq
            variant["t"][stop_id][mask].append(normalized_minute)
            processed += 1
            if processed % 1000000 == 0:
                print("Scheduled stop records:", processed, flush=True)
        if not processed:
            raise ValueError("No usable GTFS stop times found")
        print("Scheduled stop records:", processed, flush=True)

        line_variants = defaultdict(list)
        for variant in variants.values():
            if not variant["t"]:
                continue
            ordered = sorted(variant["stops"], key=lambda s: (variant["stops"][s], s))
            stops = [{"id": sid, "name": stop_meta[sid][1], "code": stop_meta[sid][0]} for sid in ordered]
            trip_sets = {
                sid: [[mask, *sorted(set(values))] for mask, values in sorted(variant["t"][sid].items())]
                for sid in ordered
            }
            line_variants[variant["line"]].append({
                "id": variant["id"], "name": variant["name"], "agency": variant["agency"],
                "alternative": variant["alternative"], "route_desc": variant["route_desc"],
                "stops": stops, "t": trip_sets
            })
        actual_lines = []
        total_bytes = 0
        for line, entries in sorted(line_variants.items()):
            # Do not use untrusted line numbers as filesystem paths.
            filename = hashlib.sha256(line.encode("utf-8")).hexdigest()[:20] + ".json"
            payload = json.dumps({"routes": entries}, ensure_ascii=False, separators=(",", ":"))
            path = output_tmp / "data" / "lines" / filename
            path.write_text(payload, encoding="utf-8")
            total_bytes += path.stat().st_size
            actual_lines.append([line, filename])
        metadata = {
            "format": 2, "source": URL, "start": start.isoformat(),
            "days": DAYS, "dayStarts": "03:00",
            "updated": datetime.now(ZoneInfo("Asia/Jerusalem")).isoformat(timespec="seconds"),
            "lines": actual_lines, "routeVariants": len(variants)
        }
        (output_tmp / "data" / "index.json").write_text(
            json.dumps(metadata, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        print("Output:", len(actual_lines), "line files;", round(total_bytes / 1048576, 2), "MiB JSON", flush=True)
        if len(actual_lines) < 20:
            raise ValueError("Unexpectedly few routes in export")
    if out.exists():
        shutil.rmtree(out)
    os.replace(output_tmp, out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--zip", dest="zip_path", type=Path)
    p.add_argument("--output", type=Path, default=Path("_site"))
    p.add_argument("--start", help="First transport day ISO YYYY-MM-DD (default: today in Israel)")
    args = p.parse_args()
    start = date.fromisoformat(args.start) if args.start else datetime.now(ZoneInfo("Asia/Jerusalem")).date()
    zip_path = args.zip_path or Path("/tmp/lzm-gtfs.zip")
    if not args.zip_path:
        download(zip_path)
    build(zip_path, args.output, start)


if __name__ == "__main__":
    main()
