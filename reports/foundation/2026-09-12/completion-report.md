# Foundational nationwide acquisition completion report

Run ID: `foundation_7dbd9a143e9504e7`
Status: `passed_with_warnings`

## Completed

- S001: `3320` target-age rows and `332` subzone proxy rows.
- S003: `332` MP2019 subzone geometries.
- S004: `337` schools; `330` have exact-postal OneMap coordinates.
- S005: `613` MRT exit points.
- S006: `5205` bus-stop points.
- S001–S003 geography matches: `332`; unmatched `0`; ambiguous `0`.

## Preserved limitations

- S001 counts are rounded to the nearest 10; summed ages compound that source precision limitation. The raw ZIP remains excluded from publication because resource-specific redistribution permission is unestablished.
- S003 is the indicative MP2019 no-sea boundary layer.
- S004 contains no native coordinates. Exact-postal S007 search resolved `330` records; unresolved/ambiguous records remain null.
- S007 preflight walking routes succeeded `30/30`; PT routes succeeded `19/30` with `11` explicit missing routes and no rate limiting. Missing PT routes require the documented walking/proximity fallback and were not imputed.
- MRT exits are access points, not station schedules or travel-time observations; bus stops contain no service or timetable information.

## Unresolved school coordinates

- ANGLICAN HIGH SCHOOL (`487012`): `ambiguous_exact_postal_coordinates`
- ASSUMPTION ENGLISH SCHOOL (`678117`): `ambiguous_exact_postal_coordinates`
- CANOSSA CATHOLIC PRIMARY SCHOOL (`387621`): `ambiguous_exact_postal_coordinates`
- CHRIST CHURCH SECONDARY SCHOOL (`737924`): `ambiguous_exact_postal_coordinates`
- HWA CHONG INSTITUTION (`269734`): `ambiguous_exact_postal_coordinates`
- RAFFLES INSTITUTION (`575954`): `ambiguous_exact_postal_coordinates`
- RIVER VALLEY HIGH SCHOOL (`649961`): `ambiguous_exact_postal_coordinates`

## Reproduce and validate

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
PYTHONPATH=src .venv/bin/python -m tuition_location_analytics.foundation.cli --repo-root .
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q src tests
.venv/bin/python -m pip check
```

An identical rerun reuses checksum-verified immutable snapshots and the redacted school-geocode cache; it makes no further network request and reproduces the processed/report file checksums.

## Boundary respected

No competitor source, national routing matrix, node score, financial model or dashboard was created.

## Exact next implementation task

Construct and manually audit versioned MRT station complexes and the evidence-qualified commercial-node inventory from these foundational layers. Resolve any remaining school-coordinate exceptions explicitly. Do not run national routing or scoring until the candidate inventory and travel thresholds are frozen.
