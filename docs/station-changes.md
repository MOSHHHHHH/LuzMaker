# What changes at your stop?

`changes.html` explains passenger-facing changes, rather than tracking Ministry
publication revisions. The default view is **all**. Public stop numbers identify
stations; equal names and opposite directions are never silently combined.
Saved stations are stored in this browser under `luzmaker-saved-stations-v1`,
independently of saved timetable groups. Nearby stops can be saved individually.

## Weekly semantics

For every fully covered transport day D, compare its latest available schedule
with the latest available schedule for D+7. A card's effective date is D+7. The
same feed supplies both days when available; otherwise they can come from different
feeds. A newer feed replaces only dates it fully covers. Earlier observations,
including future dates beyond a shorter feed, are preserved. Corrections replace
old results; publication changes are not presented as passenger alerts.

The transport day runs from 03:00 to 02:59:59 in Asia/Jerusalem. Exact seconds,
GTFS times over 24:00, pickup restrictions, simultaneous departures and repeated
public stop codes are preserved. Station/variant identity uses operator, public
line, direction and official `route_desc`, with headsign as a fallback.

Coverage is recorded independently of positive departures. Covered absence means
no service; unknown or partial dates cannot prove a cancellation. Conservative
edge coverage uses both previous and current midnight shifts. A first feed can
already establish weekly differences; no second publication is required.

Identical changes are grouped in date order with "החל מ־" and the first affected
date. A different intervening change or a gap longer than a week starts a new
card. Returning to an earlier schedule creates its own weekly comparison, not a
revision of an old card. Exact affected dates and their D/D+7 pairs remain visible
in details. Holidays are compared as actual service dates, without inventing an
operating calendar from holiday names.

## Tags and details

`weekly_changes.py` compares departure multisets and route sequence hashes.
Tags select concrete wording (earlier OR later, increased OR decreased), never
slash-separated alternatives. Added early/late journeys are claimed only when
all previous departures remain. Otherwise the observed first/last change is
reported without claiming that a specific journey moved. Interior time changes
are detected even with unchanged count, first departure and last departure.
Route and schedule flags are independent, allowing both to change together.

Every card has a "ראה פרטים" button. Schedule changes show all exact departures,
counts, first/last differences and added/removed multiplicities. Route changes
show both ordered stop sequences, additions and removals. A route-only change
does not show schedule details. Combined changes show both. A date picker exposes
every grouped pair. Acquisition timestamps are secondary source information,
not a claim about the original publication timestamp.

## Storage, migration and publication

The Python pipeline uses streamed GTFS input and scratch SQLite, with compressed
SQLite as its durable state. Repeated per-station/day profiles share date masks.
Coverage stores disjoint masks by variant and acquisition timestamp. Browsers
fetch small per-station summaries; full profiles and route definitions are loaded
on demand from `details/<station-hash>.json` and shared across comparisons.

Schema v4 restores v3 state without deleting it. It preserves profiles and route
definitions, seeds coverage only for provably complete dates in the previous
snapshot, and rebuilds weekly events. V3's publication revision events are not
imported as weekly passenger changes. Historical v3 dates whose full coverage
cannot be established remain unproven, rather than being interpreted as absence.
The bundle validator accepts v3 for restoration and verifies v4 day pairs and
all profile/route detail references before promotion.

Corrupt state, malformed input, missing trip times, unsupported frequency feeds,
and suspicious nationwide feed shrinkage fail without replacing valid output.
State and site data remain one immutable release asset with checksummed manifest,
serialized history writers, retained previous asset and atomic Pages deployment.
Pages retains the current live site until v4 weekly data is available. Changes
to the weekly pipeline trigger its build; successful completion triggers Pages.
No production state is reset by deployment.

Open Bus bootstrap samples the start of the rolling month and yesterday when no
state exists. It recovers available schedules, not every intermediate revision.
Archive failures are explicit; the official feed must still validate. Existing
state is never silently discarded. Original archive metadata and acquisition
stamps are kept separate.

## Validation

```sh
python -m unittest discover -s tests -v
node tests/ui-smoke.cjs
node tests/changes-browser-smoke.cjs
node tests/station-tools-browser-smoke.cjs
node tests/pdf-print-smoke.cjs
```

Integration checks cover latest-day replacement, cross-publication D+7 pairs,
shorter horizons, midnight edges, resumption of an earlier schedule, v3 migration,
state/bundle recovery and full details. Browser checks exercise both search
entry paths, same-name stations, platform aggregation, saved stations, default
all, conditional details, retry states, mobile layout, 03:00 rollover, unsaved
edits and existing PDF/CSV exports. National-scale performance figures in older
validation reports predate this schema and must not be treated as v4 measurements.
