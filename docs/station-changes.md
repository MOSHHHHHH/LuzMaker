# Station change detector

The static page `changes.html` is linked from the timetable homepage. All data is
built using the Python standard library. SQLite is **build-time only**; browsers
fetch a small index and a hashed per-station JSON file. Existing timetable,
Hebrew-calendar, CSV and print code is unchanged.

## Semantics

We compare successive observations of **the same transport date**, never Monday
against Tuesday. The rolling start is the same day of the previous calendar
month, clamped to its last day. The service horizon is enumerated from active
calendars and addition/removal exceptions for referenced services. Every future
service date is included; there is no 14/45/90-day cutoff. A transport date can
extend beyond the calendar horizon because of overnight trips.

Times are exact seconds. `(seconds - 10800) // 86400` maps departures into the
03:00–02:59 day and preserves GTFS times beyond 24:00. Each stop's departure is
mapped independently, matching the existing timetable builder. Pickup-disabled
stops stay in the route display but do not create boardable departures.

Identity uses operator, public line number, direction and the official Israeli
`route_desc` (line licensing/direction/alternative code), falling back to trip
headsign for feeds without that field. Public stop codes, including their order
and repetitions, identify route sequences. Volatile route, trip and internal
stop IDs do not identify a change. Without official variant metadata, equal
headsigns can group variants; this fallback cannot establish perfect identities
for arbitrary non-Israeli feeds.

Partial transport dates at feed edges are excluded from comparison, separately
for each variant. Its minimum/maximum midnight shifts determine which source
service dates are required. Only dates fully covered in both publications can
prove additions or cancellations. Complete historical observations are preserved
when the next feed begins with only a partial night.

A first observation is a baseline, including newly extending future horizons.
Events record the affected date, actual ingestion/detection timestamp, stable ID,
revision, prior revision ID, service count, first/last departure and mean gap.
Route events include added/removed stops. Later reversions replace the prior
revision for that station/date/variant and receive a new ID. Other service dates
retain their own revisions. A holiday calendar changing between publications is
a real published revision; an ordinary difference between holiday and weekday
schedules is not compared.

## Compact storage and failure handling

Stop times are streamed into an external SQLite sorter, then processed one trip
at a time. Per-station/day profiles are content addressed; equal profiles across
dates share a bitmask. Stop sequences are shared across profiles. Station JSON
also shares route definitions across all events instead of repeating full routes
for each effective date. No nationwide station × date tree is held in memory.
Only the current compressed state plus latest event revision is retained.

Required tables, references, trip sequences, calendars, clocks and restored
SQLite integrity are checked. Missing times or unknown stop references fail the
build. A decrease of more than 20% and 100 records in route/stop counts, or more than
50% and 100 records in trip/stop-time counts, or a loss of over half the active
station profiles and 100 profiles,
requires investigation; it is not published as mass cancellations. These guards
can also block legitimate large network changes and should be investigated
before deliberately accepting a new baseline. No automatic reset occurs.
Frequency-based `frequencies.txt` feeds are explicitly rejected pending expansion
support (the tested official feed contains none). GTFS departures over seven days
are rejected as a corruption guard; service-date horizons have no cutoff.

Builds use temporary files. Failed builds do not advance the durable state.
The daily workflow uploads state and validated output as one immutable GitHub
Release asset, then normally pushes a small manifest to `changes-history`.
A rejected Git push leaves the prior manifest valid. The manifest includes a
SHA-256 checksum. Its current and previous release assets are retained; uploaded
orphans and older assets are removed only after a successful manifest commit.
This keeps binary snapshots out of Git history and has no artifact-expiry limit.
The prerelease `station-change-state` and its assets must not be manually deleted.
The existing preliminary JSON state schema is intentionally not silently imported.
If a legacy history branch exists, migrate it explicitly before enabling this
version. No such branch existed during development.

GitHub Actions serializes history writers. Pages reads a complete manifest and
asset, validates both, and deploys an atomic Pages artifact. It is triggered after
a successful history run as well as by the existing timetable schedule. A failed
history or Pages build preserves the last deployment. Timetable generation and
station processing remain separate; the detector cannot mutate timetable output.

## Historical coverage

`backfill_changes.py` attempts two full snapshots from the public
[Open Bus archive](https://github.com/hasadna/open-bus-pipelines/blob/main/STRIDE_ETL_PROCESSES.md):

- The start of the rolling month, as a baseline for historical service dates.
- Yesterday, to establish a recent published comparison before today's feed.

Archive paths are
`https://openbus-stride-public.s3.eu-west-1.amazonaws.com/gtfs_archive/YYYY/MM/DD/israel-public-transportation.zip`.
The original URL, archive date and HTTP Last-Modified are recorded separately.
All event detection timestamps are **ingestion time**, never an invented original
publication time. These sampled snapshots restore historical schedules; they do
not reconstruct every daily publication or every reverted change in the gap.
The UI states this limitation. Archive failure is logged and initialization falls
back to the earliest snapshot actually obtained. The next official feed must
still validate successfully before anything is published.

A complete daily archive replay can be performed using `changes_pipeline.run`
with each snapshot's service date, in chronological order; it is intentionally
not presented as having happened in the two-snapshot bootstrap.

## Run and validate

```sh
python -m unittest discover -s tests -v
python scripts/backfill_changes.py --state work/state.sqlite.gz --output work/changes
python scripts/build_changes.py --zip /path/to/official.zip --state work/state.sqlite.gz --output work/changes
python scripts/change_bundle.py bundle work work/bundle.zip
node tests/changes-browser-smoke.cjs  # playwright + Chromium
```

The index reports measured build time, peak process memory (Linux ru_maxrss),
input counts, service horizon, transport dates processed, compressed state size,
published JSON bytes and event counts. Archive and current builds should be run
in separate Python processes when comparing individual peak memory values.
