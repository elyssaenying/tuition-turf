# Station-complex and commercial-node data-quality report

Run ID: `nodes_0a34bc5be80d0c27`
Overall status: `passed_with_warnings`

| Check | Table | Status | Observation |
|---|---|---|---|
| `NQ01` | `station_complex_exits` | `pass` | 613/613 source exits preserved exactly once |
| `NQ02` | `station_complexes` | `warning` | 188 exact-name complexes; 12 carry review flags |
| `NQ03` | `station_complexes` | `warning` | S026 corroborated 160 complexes; 28 unmatched complexes retained |
| `NQ04` | `mp2025_relevant_land_use` | `warning` | 10148 accepted-category features from 113394 MP2025 features; 3 invalid source geometries, none silently used without validation/repair |
| `NQ05` | `commercial_node_candidates` | `pass` | 146 MRT candidates; statuses {'needs_manual_review': 5, 'provisional': 141}; missing evidence remains null |
| `NQ07` | `station_overrides` | `pass` | 7 station-override labels applied; 0 configured override labels were not found in this exit snapshot |
| `NQ10` | `operational_status_evidence` | `pass` | 1 known operational exceptions applied (S026 plays no role in operational_status; identity/name/code/line corroboration only); 0 configured known exceptions were not found in this exit snapshot; 177 system-map roster (S032 v2026-09-13.1) names matched a complex in this snapshot |
| `NQ08` | `station_complexes` | `pass` | operational_status counts {'not_operational': 1, 'verified_operational': 187} |
| `NQ11` | `station_complexes` | `pass` | Every verified_operational complex carries either a non-empty operational-status evidence reference (identity override or known-exception evidence) or a match against the current dated System Map roster; S026 corroboration and mere presence in the S005 exit layer are never, by themselves, sufficient. |
| `NQ09` | `node_review_queue` | `pass` | 18 review rows; 6 open, 12 closed; issue categories {'excluded_not_yet_operational': 1, 'no_commercial_zoning_signal': 5, 'repeated_exit_labels': 6, 'unusually_dispersed': 6} |
| `NQ06` | `reportable_node_outputs` | `pass` | generic scan pass; exact comparison performed; 0 finding files |

A failure blocks phase approval. Warnings and limited assurance remain explicit and are not converted to passes.
