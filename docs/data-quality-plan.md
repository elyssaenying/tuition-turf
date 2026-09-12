# Data-quality plan

Status: planned validation, not executed analysis tests. This pass has no datasets, fixtures or calculation code. Implement meaningful checks alongside the relevant transformations; use synthetic test fixtures only when implementing tests, clearly isolated from analytical outputs. Never publish fixtures as observations or findings.

## Test and review matrix

| Check ID | Layer | Required validation | Failure treatment |
|---|---|---|---|
| Q01 | Source/ingestion | Enforce the six-value source enum and its evidence rules: opened URL plus timestamp for `accessible_unconfirmed`; opened URL, inspected relevant content/metadata and timestamp for `verified_usable`/`verified_limited`; attempted-access timestamp for `unavailable`; timestamp, reason and reviewed evidence for `rejected`; null verification timestamp for `unverified`. Review licence/access, vintage, immutable snapshot checksum and schema; detect unexpected schema drift. | Block acquisition/publication where access, inspection or provenance requirements are unmet |
| Q02 | All tables | Declared grain unique; required keys/statuses present; types/enums/ranges valid; foreign keys resolve; join row counts reconciled | Block the affected stage; prevent many-to-many join inflation |
| Q03 | Population | No negative counts or overlapping age groups in chosen aggregates; suppression is null; population basis consistent; proxy formula and retained inputs reconcile | Block invalid calculations; flag unavoidable approximations |
| Q04 | Age proxy | Independently verify known single-age/grouped cases, inclusive endpoints and conservative bounds; ensure alternate cohort methods disclose unidentifiable shifts | Block formula errors; document approximation limits |
| Q05 | Geography | Geometry validity, CRS/coordinate order, Singapore-domain plausibility, correct boundary versions, hierarchy and crosswalk population reconciliation | Block wrong geometry/joins; flag genuine boundary ambiguity |
| Q06 | Catchments | Allocation shares bounded; allocated totals reconcile within a declared precision tolerance; barrier/mode/anchor assumptions visible; overlapping nodes never sum as disjoint demand | Block conservation errors; flag routing/proximity limitations |
| Q07 | Branch identity | Brands and branches separated; address/unit/postal matches reviewed; duplicate, relocation and closure cases adjudicated | Block known duplicate counts; bound uncertain cases |
| Q08 | Offerings and coverage | Mathematics/level overlap validated per branch; online-only/out-of-scope excluded from direct counts; confirmed and possible counts reconcile to branch records; competition exposure has a declared method and quality flags; per-1,000 rate remains descriptive; missing coverage is not zero competition | Block unsupported confirmed counts or exposure; publish coverage and uncertainty |
| Q09 | Premises | Enforce `verified_eligible|screened_feasible|ineligible|unresolved`; verify public-screening versus unit-specific evidence scope, recency and cost scenario; every mandatory check needs unit-specific authoritative pass evidence for `verified_eligible` | Block lease-ready/full recommendations without `verified_eligible`; allow only clearly conditional node conclusions from `screened_feasible`; exclude `ineligible` and retain `unresolved` as investigation leads |
| Q10 | Finance units | Monthly versus term/annual values converted explicitly; SGD consistent; no staff/rent/launch cost double counting; nonnegative costs and valid capacity | Block inconsistent scenarios |
| Q11 | Break-even | Independently hand-check linear boundary cases, integer ceiling, nonpositive contribution, zero fixed costs, zero capacity and capacity limits; stepped-cost search checks feasible schedule and surplus discontinuities | Block invalid break-even/feasibility outputs |
| Q12 | Cash flow | Month 0 and opening requirement reconcile; cash receipts/payments, deposit treatment, cumulative balances and peak deficit reconcile; payback requires sustained recovery over remaining horizon | Block incorrect cash/payback outputs |
| Q13 | Demand/capacity | Participation and capture in `[0,1]`; unique students reconcile with seat-slots and level mix; scenarios exceeding capacity flagged rather than silently clipped | Block unit errors; expose unmet-demand/capacity limits |
| Q14 | Pareto | Hand-check strict dominance, equal alternatives, ties/tolerance, mixed directions, missingness, premises status and distinct scenario sets; confirm competition exposure, rather than per-1,000 diagnostic, is the primary competition input; input ordering cannot change frontier membership | Block incorrect comparison status |
| Q15 | Sensitivity and hypotheses | Baseline reproducible; H2/H3 materiality definitions frozen before final inspection; plausible scenario grid explicit and versioned; dependencies and adverse combinations coherent; H4 non-dominated share uses the full grid and tests the 70% threshold; frequencies label their denominator and are not probabilities | Block post-results threshold selection, misleading probabilities or inconsistent cases |
| Q16 | Static export | JSON schema, finite numbers/null reasons, table references and geometry IDs valid; manifest checksums/counts/versions agree; no private data/secrets or prohibited redistribution | Block release |
| Q17 | Interpretation | Every finding linked to output/evidence; no causal or exact-age claims from proxies; education-cluster effects labelled exploratory unless a confirmatory test is supported and kept separate from competition; at most three final nodes per scenario | Correct narrative before release |

Use numerical tolerances justified by source precision, coordinate transformations and rounding; record them before accepting a run. Do not hide discrepancies behind an arbitrary generous tolerance. SHA-256 is the provisional snapshot/bundle checksum choice, subject to implementation review.

## Branch validation protocol

Review all branches contributing to final shortlisted catchments, including uncertain branches that materially change comparisons. Record who checked what, against which sources, at what time, and the outcome. Broader-screening audits should be stratified across geography, independent/chain providers, geocode quality and ambiguous scope; define sample size after inventory size is known. Review chain-wide assumptions at branch level: a brand-wide mathematics page alone cannot establish a local timetable. Correct any discovered systematic issue across the inventory, not only sampled records.

Use confirmed-count lower cases and plausible-inclusive scenarios to communicate incompleteness; these are not statistically guaranteed market bounds when undiscovered providers may exist. Duplicate detection can nominate pairs but cannot automatically merge similarly named independent providers without evidence.

## Gates and exceptions

`Blocker` issues stop the affected stage or publication. Examples include a lease-ready claim without `verified_eligible` evidence, invalid joins, broken financial calculations and missing provenance. `Warning` issues permit limited analysis only with explicit scope, sensitivity treatment and an accepted-limitation record. A premises with current public evidence showing no known blocker may receive `screened_feasible` and support a clearly conditional node shortlist when its cost scenario is evidenced; the remaining permission or landlord confirmation must remain visible. `Info` issues are annotations. Do not downgrade a blocker merely to obtain three recommendations.

Critical missing fields exclude an alternative from the affected comparison as `insufficient_data`; preserve the record and its reason. Missing competition coverage cannot become a favourable score. Missing final permission or landlord confirmation prevents `verified_eligible`, regardless of apparently strong demand, but does not prevent `screened_feasible` when public screening is complete and reveals no known blocker.

Write a machine-readable quality report keyed to run/table/record/check plus a readable release summary. Deterministic transformations should produce equivalent outputs from identical inputs/configuration. Repeat stochastic analyses using the recorded seed and documented numerical tolerance. Tests should target invariants and independently derived expected values, not repeat the same implementation as the oracle.

## Manual analytical review

Before release, inspect map joins and representative geocodes, reconcile screened-area totals, trace every shortlisted node to source/assumption evidence, recalculate representative financial cases independently, and review conclusions under adverse scenarios. A polished dashboard is not a substitute for these checks. Current-pass verification is limited to document/structure consistency and absence of prohibited implementation artifacts.
