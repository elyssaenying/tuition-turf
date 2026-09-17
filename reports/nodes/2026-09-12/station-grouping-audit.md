# MRT station-complex grouping audit

Run ID: `nodes_afd024de462faab3`

- Input S005 exits: `613`
- Membership rows: `613`
- Exact-name station complexes: `190`
- Named MRT complexes: `142`
- LRT complexes retained but not promoted to MRT node candidates: `41`
- Code-only or unknown complexes: `7`
- Complexes with repeated exit labels: `6`
- Complexes exceeding the dispersion review threshold: `6`
- S026 exact-name corroboration matches: `160`
- S026 unmatched complexes retained: `30`

Grouping rule: Exact case/whitespace-normalized S005 station name; no fuzzy or distance-based merge/split.

Review-threshold rationale: The 400 m threshold equals the smallest fixed commercial-evidence proximity band, so a wider exit set can materially change exit-union buffer evidence. It is a review trigger, never a grouping rule.

No fuzzy matching, distance-based merging or silent splitting was used. Later accessibility must use the closest valid member exit, not the representative point or centroid.
