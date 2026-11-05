#!/usr/bin/env python3
"""Check the freshness of the *published* LuzMaker GTFS catalog (not the repository).
Exit nonzero if it is missing, invalid or older than 30 hours.
"""
import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone

DEFAULT_URL = "https://moshhhhhh.github.io/LuzMaker/data/index.json"
MAX_AGE_HOURS = 30


def age_hours(payload, now=None):
    if payload.get("format") != 2 or not payload.get("lines"):
        raise ValueError("Published GTFS catalog is invalid or empty")
    raw = payload.get("updated")
    if not isinstance(raw, str):
        raise ValueError("Published GTFS catalog has no updated timestamp")
    updated = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if updated.tzinfo is None:
        raise ValueError("GTFS updated timestamp must include a time zone")
    now = now or datetime.now(timezone.utc)
    elapsed = (now - updated).total_seconds() / 3600
    if elapsed < -0.25:
        raise ValueError("GTFS timestamp is implausibly far in the future")
    return max(0, elapsed)


def check(url=DEFAULT_URL):
    last = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(
                url + ("&" if "?" in url else "?") + "freshness=" + str(int(time.time())),
                headers={"User-Agent": "LuzMaker-Freshness-Monitor/1.0", "Cache-Control": "no-cache"},
            )
            with urllib.request.urlopen(request, timeout=25) as response:
                payload = json.load(response)
            hours = age_hours(payload)
            print(f"Published GTFS dataset age: {hours:.2f} hours; maximum: {MAX_AGE_HOURS} hours", flush=True)
            if hours >= MAX_AGE_HOURS:
                raise ValueError(f"Published GTFS dataset is stale ({hours:.1f}h >= 30h)")
            return
        except Exception as error:
            last = error
            print(f"Attempt {attempt + 1}/3: {error}", file=sys.stderr, flush=True)
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
    raise SystemExit(f"Freshness check FAILED: {last}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    args = parser.parse_args()
    check(args.url)
