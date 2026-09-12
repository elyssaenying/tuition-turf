# Foundational data-quality report

Run ID: `foundation_7dbd9a143e9504e7`
Overall status: `passed_with_warnings`

## Check results

| Check | Source/table | Status | Observation |
|---|---|---|---|
| `Q02` | S001 / `population_age_7_16` | `pass` | 0 duplicate source composite keys |
| `Q03` | S001 / `population_proxy_subzone` | `pass` | 0 invalid/missing population conditions; 37800 nil-or-negligible source markers treated as zero |
| `Q03` | S001 / `population_sex_reconciliation` | `pass` | 0 missing sex sets; maximum Total-(Males+Females) difference 10 |
| `Q04` | S001 / `population_proxy_subzone` | `warning` | Each published count is rounded to the nearest 10; sums preserve but compound that limitation. |
| `Q05` | S003 / `mp2019_subzones` | `pass` | 0 blocking geometry, bounds, identifier or hierarchy conditions |
| `Q05` | S003 / `mp2019_subzones_source_geometry` | `warning` | 6 source geometries required recorded make_valid repair; 0 processed geometries remain invalid |
| `Q05` | S001+S003 / `geography_crosswalk` | `pass` | 332 matched, 0 unmatched, 0 ambiguous; no fuzzy matches |
| `Q02` | S004 / `schools` | `pass` | 0 blocking school key/required-field/postal conditions |
| `Q05` | S004+S007 / `schools` | `warning` | 330 coordinates validated; 7 unresolved or absent |
| `Q05` | S005 / `mrt_exits` | `pass` | 0 blocking point geometry/key/bounds conditions; 0 duplicate coordinates retained for review |
| `Q02` | S005 / `mrt_exits` | `warning` | 8 repeated descriptive business keys across unique source point IDs |
| `Q05` | S006 / `bus_stops` | `pass` | 0 blocking point geometry/key/bounds conditions; 0 duplicate coordinates retained for review |
| `Q02` | S006 / `bus_stops` | `pass` | 0 repeated descriptive business keys across unique source point IDs |
| `Q06` | S007 / `routing_preflight` | `warning` | walking 30/30; PT 19/30; PT missing routes 11; rate limited 0 |

Warnings preserve the affected limitation; failures block release of the affected table. No failed check is downgraded to make the run pass.
