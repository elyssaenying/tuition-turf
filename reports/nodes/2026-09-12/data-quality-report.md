# Station-complex and commercial-node data-quality report

Run ID: `nodes_afd024de462faab3`
Overall status: `passed_with_warnings`

| Check | Table | Status | Observation |
|---|---|---|---|
| `NQ01` | `station_complex_exits` | `pass` | 613/613 source exits preserved exactly once |
| `NQ02` | `station_complexes` | `warning` | 190 exact-name complexes; 19 carry review flags |
| `NQ03` | `station_complexes` | `warning` | S026 corroborated 160 complexes; 30 unmatched complexes retained |
| `NQ04` | `mp2025_relevant_land_use` | `pass` | 10148 accepted-category features from 113394 MP2025 features |
| `NQ05` | `commercial_node_candidates` | `pass` | 149 MRT candidates; statuses {'needs_manual_review': 23, 'provisional': 126}; missing evidence remains null |
| `NQ06` | `reportable_node_outputs` | `warning` | generic scan pass; exact comparison not_performed_credentials_unavailable; 0 finding files |

A failure blocks phase approval. Warnings and limited assurance remain explicit and are not converted to passes.
