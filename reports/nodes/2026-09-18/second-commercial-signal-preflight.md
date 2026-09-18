# Second commercial-signal preflight

Decision: **ACCEPTED**
Source: `S034` — Retail pharmacy locations (GEOJSON)
Snapshot: `2026-09-18`

## Plain-English meaning

The source passed every rule frozen before its node-level results were inspected. It may be used as an independent positive commercial-presence signal.
A nearby licensed pharmacy shows current public-facing retail activity. It does not prove that a tuition unit is available, affordable or permitted. No nearby pharmacy does not prove that commercial activity is absent.

## Gate results

| Gate | Status | Observed | Required |
|---|---|---:|---:|
| feature_count | pass | 249 | >=100 |
| valid_in_bounds_point_rate | pass | 1.000 | >=0.99 |
| source_age_months | pass | 10.316 | <=18 |
| planning_region_count | pass | 5 | >=5 |
| minimum_source_points_per_region | pass | 16 | >=10 |
| unassigned_source_point_rate | pass | 0.000 | <=0.01 |
| unassigned_node_count | pass | 0 | <=0 |
| national_node_coverage_rate | pass | 0.658 | >=0.45 |
| minimum_region_node_coverage_rate | pass | 0.412 | >=0.25 |
| positive_nodes_nationally | pass | 96 | >=36 |
| minimum_positive_nodes_per_region | pass | 7 | >=2 |

## Regional coverage at 800 m

| Planning region | Pharmacy points | MRT areas | Positive MRT areas | Coverage |
|---|---:|---:|---:|---:|
| CENTRAL REGION | 130 | 85 | 63 | 74.1% |
| EAST REGION | 37 | 17 | 7 | 41.2% |
| NORTH REGION | 16 | 11 | 7 | 63.6% |
| NORTH-EAST REGION | 31 | 14 | 9 | 64.3% |
| WEST REGION | 35 | 19 | 10 | 52.6% |

## Method

- Each MRT area uses the union of straight-line buffers around every preserved station exit.
- A node is positive when at least one distinct HSA-registered retail pharmacy falls within the buffer.
- The 800 m band is the qualification band; 400 m is retained as a stricter sensitivity view.
- This preflight does not inspect tuition competitors and does not select candidate winners.
