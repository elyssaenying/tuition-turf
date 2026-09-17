# MRT station-complex grouping audit

Run ID: `nodes_0a34bc5be80d0c27`
Station-override config version: `2026-09-13.2`
Review-disposition config version: `2026-09-13.2`

- Input S005 exits: `613`
- Membership rows: `613`
- Exact-name station complexes: `188`
- Named MRT complexes: `147`
- LRT complexes retained but not promoted to MRT node candidates: `41`
- Code-only or unknown complexes: `0`
- Complexes with repeated exit labels: `6`
- Complexes exceeding the dispersion review threshold: `6`
- S026 exact-name corroboration matches: `160`
- S026 unmatched complexes retained: `28`
- Station overrides applied (source labels resolved): `7`
- Configured override labels not found in this exit snapshot: `[]`
- Operational-status counts: `{'not_operational': 1, 'verified_operational': 187}`
- Station-level review items open/closed: `0` / `12`

Grouping rule: Exact case/whitespace-normalized S005 station name; no fuzzy or distance-based merge/split. Authoritative station overrides are applied before grouping, never by proximity alone.

Review-threshold rationale: The 400 m threshold equals the smallest fixed commercial-evidence proximity band, so a wider exit set can materially change exit-union buffer evidence. It is a review trigger, never a grouping rule.

No fuzzy matching, distance-based merging or silent splitting was used. Every merge or rename is backed by an authoritative station-code or opening-date override, never coordinates alone. Later accessibility must use the closest valid member exit, not the representative point or centroid.

## Previous-to-current station-complex mapping

| Previous label | Previous complex ID | Resolution | New station name | New complex ID | Merged into pre-existing complex | Operational status |
|---|---|---|---|---|---|---|
| `CC31` | `STC_4F67A2B7F9D4250B` | rename_separate_station | `CANTONMENT MRT STATION` | `STC_DC97B3FEE66D683C` | False | `verified_operational` |
| `DT4` | `STC_D24CB8B656B5586E` | rename_separate_station | `HUME MRT STATION` | `STC_28B6579C873901A9` | False | `verified_operational` |
| `CC30` | `STC_11CBC8AA03750468` | rename_separate_station | `KEPPEL MRT STATION` | `STC_EED39143B2C1F15F` | False | `verified_operational` |
| `CC9` | `STC_0E422209C21B8305` | merge_into_existing_named_complex | `PAYA LEBAR MRT STATION` | `STC_4ABC3968FE0952BD` | True | `verified_operational` |
| `CC32` | `STC_FD3E9A7EF2B560F6` | rename_separate_station | `PRINCE EDWARD ROAD MRT STATION` | `STC_9E7B3475E29B8CA9` | False | `verified_operational` |
| `NE18` | `STC_EF95E6CC2102EECD` | rename_separate_station | `PUNGGOL COAST MRT STATION` | `STC_A0664BB74646EC10` | False | `verified_operational` |
| `DT18` | `STC_3242262A0AD08B70` | merge_into_existing_named_complex | `TELOK AYER MRT STATION` | `STC_A18DD95E5E5056FA` | True | `verified_operational` |
