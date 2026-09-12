# Two-source preflight report

Generated: 2026-09-12T09:08:07+00:00

## Boundary

Only S001 was acquired. S007 was limited to the fixed fixture and was skipped if credentials were unavailable. No other dataset, competitor source, premises source or national routing matrix was acquired.

## S001 — Population Trends 2025 geospatial ZIP

- Status: `completed_with_limitations`
- Storage: `data/raw/s001_population_trends_2025/2026-09-12/population-trends-2025-geospatial.zip`
- Bytes: `9568844`
- SHA-256: `3008a865bc85e06693a8a8456d464e8a2a0661f2c5aa8dc863dd2c90a5448e2f`
- Requested/final URL match: `True`
- HTTP status: `200`
- T3 candidates: `geospatial-data2025/Singapore Residents by Planning Area, Subzone, Single Year of Age and Sex, Jun 2025.xlsx`
- Full dataset loaded/transformed: `False`
- Raw redistribution: `unestablished_for_raw_redistribution`

The archive listing and bounded T3 header/schema inspection are recorded in the machine-readable result. Raw redistribution remains unapproved unless the resource-specific terms are established.

## S007 — OneMap routing

- Status: `completed`
- Fixture: `config/preflight/onemap_od_fixture.json`
- Planned search requests: `13`
- Executed search requests: `13`
- Planned route requests: `60`
- Executed route requests: `60`
- Journey date/time: `09-16-2026 16:00:00`

Only redacted aggregate/request metadata is persisted; authentication material and raw route responses are not stored.

## Validation

- Independent S001 checksum match: `True`
- S007 route boundary respected: `True`
- Secret-like values in reportable files: `[]`

## Remaining blockers

- S001 resource-specific raw redistribution permission remains unestablished.
