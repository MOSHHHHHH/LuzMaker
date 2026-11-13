# Station tools, change-page UX and direct PDF export

The original change detector was merged independently in PR #1. These additions
reuse its published event data and do not change its comparison algorithm,
snapshot schema, historical state or writer workflow.

## Daily station directory

`build_gtfs.py` now also calls `station_directory.py`. It writes:

- `data/station-search.json`: unique public stop codes, names and deduplicated city references, fetched lazily
  when a user searches by name.
- `data/stations/<sha256(code)[:20]>.json`: name, official city, coordinates, precomputed nearby
  stops, freshness and route choices for that exact public code.

The full official stop inventory is searchable, including stops without bus
service in the timetable window. Route choices include only boardable variants
with service in the existing 14-day timetable export. Cities are parsed from the
official `stop_desc` field; missing cities are not guessed. Name search accepts
common station abbreviations and city words, and never reuses a stale suggestion
after the query changes. They preserve operator,
direction and alternatives. Different stops with the same name are never merged.

Platforms sharing the same public code are one selectable physical-stop variant.
The selected entry stores all relevant `stopIds`; its timetable merges departure
minutes across those platforms. Legacy saved single-platform entries retain their
original behavior. A station on the opposite side of the road remains a separate
code and is offered only through the explicit nearby-station comparison.

A latitude/longitude grid narrows candidates; the final cutoff uses the haversine
formula and the IUGG mean Earth radius, 6,371,008.8 metres. Only distances <=300m
are included. Distances are rounded for display **after** the exact cutoff. This
is straight-line distance, not a walking-route estimate. Missing/invalid positions
produce no invented neighbours. Duplicate physical codes in the tested official
feed were audited: all duplicate coordinates were identical.

The real-data build processed 7,473,325 timetable stop records, 911 public bus
numbers and 34,313 unique public stop codes. The original timetable horizon,
calendar exceptions and 03:00 convention are unchanged.

## Change-page UX

The page begins with name/number search, keyboard suggestions and an unambiguous
selected-stop heading. Nearby stops are added by explicit multi-selection, and
results retain each station's identity. Default results cover today and future
transport dates; past/today/all tabs, change category and line filters are
available. Ordinary daily repetitions with equivalent displayed change details
are grouped into cards, retaining an expandable list of **all** effective dates.
This is a presentation grouping; stored events and revision identifiers remain
unchanged.

Cards show human route names, operator, direction/alternative, effective date,
service changes and expandable route comparisons. Detection/source/archive
information remains available without dominating the search interface. A failed
metadata request is distinguished from a retired or unknown stop. No-change,
unknown-stop, loading and server-error states are separate. At 02:30 the current
transport date is still yesterday, so today's 03:00 changes remain upcoming.

## Direct vector PDF

`pdf.js` creates an A4 PDF with jsPDF 4.2.1. Fonts and libraries are self-hosted and
loaded on demand. Unicode BiDi uses bidi-js 1.0.3; Hebrew/Latin/numeric runs,
parentheses, arrows and date/time ranges are tested. Font metrics determine
wrapping and section costs, and all rows retain 9pt text. DejaVu Sans regular and
bold are embedded subsets. Source-data characters were checked against the font
cmap. Unsupported custom pictograms are replaced visibly, with a notice in the
export status; they are not silently omitted.

Every page repeats the title, shared legend and source/footer. Rows read down
four balanced columns, right to left, and continue in order. Full chunks occupy
pages first; the final chunk of each timetable is packed using the existing
bounded minimum-page search. This prevents a tail from appearing before its
first part. Long legends that cannot coexist with readable timetable rows on one
A4 produce an actionable split-group message rather than clipped text or tiny
fonts. The browser's print dialog is not used for PDF export.

Vector text remains searchable/selectable with Unicode mappings. The app logo
is the existing local SVG rendered as a small PNG; timetable text is not a
screenshot. CSV, saved groups, calendar preferences and SHES remain independent.

## Verification

- Python calendar, change-history and station-directory unit/integration tests.
- Existing UI/CSV/SHES/holiday-alias/packing regressions.
- Chromium tests of actual generated data: duplicate-name search, keyboard,
  grouping, nearby selection/removal and 300m cutoff, filtering, mobile,
  unknown/empty/error states and 02:30 semantics.
- Chromium test of adding multiple exact-stop routes, platform aggregation,
  group persistence, timetable generation, real PDF download, font failure/retry
  and CSV export.
- Independent MuPDF tests of actual PDF files: A4 bounds, embedded fonts, every
  departure retained, chronological column order, continuation order and a
  known mixed-direction string's physical glyph order. The compact fixture is
  one page; the 205-departure fixture is two pages.

The source is still a static GitHub Pages site; there is no runtime database,
external PDF conversion service or paid API.
