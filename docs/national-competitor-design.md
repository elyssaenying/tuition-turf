# National competitor-design decision

## Purpose and decision boundary

This design governs the next competitor phase only. It does not acquire any data, create a national branch inventory, calculate travel times, score nodes, model finance, rank locations or make a recommendation.

The independently audited private method pilot `competitors_pilot_1e93cdf516f542c6` is approved as a **method and controls pilot**: all 17 gates passed, with 64 retained branches, 33 brands and 2 excluded branches. Its 64 retained branches are not a Singapore-wide branch count, a market-share estimate or evidence of national coverage.

The national business question is not “how many branches are in Singapore?” It is which evidence-qualified commercial nodes are conditionally attractive for a P1–S4 Mathematics tuition centre, after comparing demand, accessibility, direct competition and transparent financial assumptions. Competition evidence must therefore be broad enough to support the final candidate-node comparison without allowing observed competition to select the nodes being compared.

## Approaches considered

| Criterion | A. Exhaustive 55-planning-area inventory | B. Frozen candidate catchments plus outside audit |
|---|---|---|
| Decision validity | Strongest basis for national descriptive branch statistics and any later all-area screening. More evidence than the final node decision necessarily needs. | Strong for node comparison if candidate nodes and catchments are frozen before competitor inspection. Does not estimate a national total. |
| Selection bias / circularity | Low after a uniform protocol, subject to channel coverage limits. | Controls decision circularity because non-competitor data selects the candidate set first. Residual selection risk is measured, not erased, through a stratified outside-candidate audit. |
| Source permissions | Highest exposure: systematic discovery may conflict with directory terms; every channel needs explicit permission. | Avoids systematic S010 use. Can be performed using operator-controlled pages and general-web discovery leads, subject to their terms and a private evidence boundary. |
| Reproducibility | High if all 55 areas receive an identical logged protocol, but expensive to keep evidence current. | High within frozen catchments and audit sample: fixed nodes, bands, templates, dates and outcome rules. It must label all non-inspected areas as out of scope. |
| Coverage claim | Can claim a protocol-bound national inventory, not completeness, if all areas are executed and limitations disclosed. | Can claim complete protocol execution within frozen candidate catchments plus a defined outside audit. It cannot claim a national branch count or national competitor coverage. |
| Manual validation burden | Potentially very large: every candidate branch found across 55 areas requires an explicit outcome. | Bounded to decision-relevant catchments plus an audit. Duplicate branches across overlapping catchments are validated once and linked to every catchment. |
| Time and cost | Highest; likely delays demand/accessibility and final comparison. | Material but feasible for a portfolio project; workload remains visible and approval-gated. |
| Portfolio credibility | Impressive only if permissions, currency and completion are genuinely sustained; an incomplete “national” inventory would weaken credibility. | Demonstrates a defensible design-of-evidence decision, pre-registration, uncertainty handling and an audit rather than an unjustified coverage claim. |
| Ability to answer this business question | Sufficient, but inefficient for a node shortlist. | Sufficient for conditional node comparison once national demand/accessibility screening and frozen catchments are complete. |
| Possible / unresolved branches | Can give national uncertainty descriptions but still cannot silently promote them. | For every candidate catchment, primary exposure is confirmed/current branches; confirmed plus possible is the upper bound; unresolved branches remain a disclosed coverage risk. Audit outcomes test whether unresolved/omitted signals concentrate outside candidate catchments. |

## Recommendation

Recommend **Approach B: two-stage, candidate-node-first competition evidence with a reproducible outside-candidate audit**.

This is not a convenience sample. It is defensible because the candidate set is selected from the approved nationwide node universe using only demand, accessibility and node-evidence fields, before any national competitor result is inspected. Competition can then affect comparison among the pre-specified alternatives, rather than determine which alternatives exist. The outside audit provides a falsifiable check on whether the non-competitor screen has created a material blind spot.

Approach A remains the preferred design if a later stakeholder needs a protocol-bound nationwide branch inventory, national market-density description, or a defensible claim about all 55 planning areas. It should not be represented as completed through Approach B.

The concise owner choices and recommended defaults are in [national-design-decision-sheet.md](national-design-decision-sheet.md). Those values remain proposals until explicitly approved.

## Required sequence before competitor inspection

The 146-node inventory is approved as an inventory, but zero nodes are currently `qualified`: MP2025 zoning supplies only one of the two required independent commercial-signal families. Therefore `approved node inventory` must not be read as `146 evidence-qualified nodes`.

The proposed execution order is:

1. apply a frozen, legally reusable, non-competitor second commercial signal to the complete 146-node universe;
2. execute the separately authorised national demand/accessibility stage with documented route fallbacks;
3. freeze the candidate-node set using only qualified status, demand, accessibility and coverage rules;
4. draw and freeze the outside-node audit sample with known inclusion probabilities; and
5. only then begin national competitor discovery.

This sequence resolves two dependencies that the first draft left implicit. A final candidate set cannot be frozen from accessibility results that do not yet exist, and nodes cannot be called evidence-qualified before the second-signal rule is executed. Neither the second-signal source nor national routing is authorised merely by this design document.

## Proposed protocol (not active until approval)

### 1. Geographic universe and unit

- Universe: the approved 146 current commercial-node candidates, not planning areas and not brands.
- Unit of competition: one physical teaching branch at one current address/unit at the analysis cutoff. Brands, offerings and evidence remain separate entities.
- Scope: operators with branch-specific evidence of Mathematics and at least one overlapping P1–S4 level, under the existing inclusion rules.
- A branch that falls in more than one frozen catchment remains one branch record and is linked to each affected catchment. It receives one validation credit, never one credit per catchment.

### 2. Freeze candidate nodes before competitor inspection

1. Reconstruct the 146-node universe from the approved node output, retaining node IDs, anchors, operational status and node-evidence flags.
2. After the second-commercial-signal rule has been executed, run the separately authorised national demand/accessibility screening using no competitor observations, branch counts, brand names or competitor locations.
3. Apply a pre-approved deterministic eligibility and stratification rule to create the candidate-node set. The freeze record must include the full input checksums, node universe, rule version, selected/rejected IDs and reasons, scenario IDs, timestamp and reviewer.
4. Publish no competitor-derived diagnostic while the freeze decision is made. Once frozen, its membership cannot change because of discovery yield or competition count; a later change requires a new version and decision-log entry.

The candidate-set size, screening threshold and scenario rule are approval decisions, not defaults. The decision sheet recommends a balanced maximum of **36 nodes**, combining deterministic demand/accessibility merit slots with predeclared regional coverage slots. It becomes binding only if approved and encoded before national results are inspected.

### 3. Catchments and sensitivity

The primary and sensitivity bands must be approved before national competitor discovery. Proposed choices are:

| Role | Proposed definition | Status |
|---|---|---|
| Primary | Union of 10-minute walks from the preserved exits of the station complex, where validated walking results exist | Requires approval and later route execution |
| Sensitivity 1 | Union of 15-minute walks from the preserved exits | Requires approval and later route execution |
| Sensitivity 2 | EPSG:3414 straight-line 800 m and 1,200 m bands, labelled `proximity_proxy` only | Requires approval; used only when route evidence is unavailable or as an explicit sensitivity |

Routes are not inferred. S007's documented missing-PT fallback remains in force: walking network evidence first, then proximity proxy if necessary; no imputed travel time. Candidate catchment geometry, overlap, source/mode, threshold and failure status must be retained.

### 4. Discovery channels and fixed templates

Permitted national discovery channels are limited to:

- operator-controlled location, contact, centre, timetable and programme pages;
- general web search as a lead-generation tool only, with query/date/result count retained but no raw result page or snippet persisted;
- an explicitly authorised open or operator-provided register if a later source review approves its precise reuse.

S010 must not be used for systematic national acquisition, bulk extraction, or public redistribution. A map pin, directory listing, search result or legal-entity record may create a lead but cannot by itself confirm a physical teaching branch.

The protocol should execute the same approved template set for every frozen candidate catchment and every outside-audit catchment. Proposed template families, requiring final wording approval, are:

1. `P1 P6 Mathematics tuition near <node/catchment place>`;
2. `Secondary Mathematics tuition near <node/catchment place>`;
3. `site:<operator-domain> <address or place> Mathematics` after an operator is identified;
4. operator-controlled locations/contact/programme-page checks for every surfaced candidate.

Each query log must record ID, catchment, template/version, channel, query text, date, outcome, candidate count and any blocked/zero-result outcome. A candidate may be linked only to the observations that surfaced it.

### 5. Identity, validation and outcome handling

Apply D44/D51 identity rules unchanged: deterministic normalisation only; optional `Blk` wording and supported missing-unit completion are handled only under the closed same-brand/same-building rule; different supported units, postal conflicts and affirmative identity conflicts remain distinct and reviewable. A branch retains every linked discovery and validation provenance record.

Every canonical candidate within a frozen catchment receives a candidate-specific operator-source attempt, including blocked, absent and inconclusive outcomes. Record separately:

1. physical address and branch identity;
2. postal code and unit where available;
3. current operation;
4. Mathematics offering; and
5. overlapping P1–S4 coverage.

Classifications are unchanged:

- `confirmed`: fresh operator-controlled branch, current-operation, Mathematics and overlapping-level evidence;
- `possible`: some branch/current evidence exists but one or more subject/level elements are incomplete; it never enters primary competition and must have a review reason;
- `unresolved`: no sufficient candidate-specific evidence or a conflict/blocked outcome; it never enters primary competition and remains an explicit coverage limitation;
- `excluded`: evidence establishes a wrong catchment/geography, closed/non-operating status, or out-of-scope offering; preserve provenance and reason.

Primary competition is confirmed + current branches in a catchment. The uncertainty upper bound is confirmed + possible; unresolved branches are not converted into a numerical upper bound and must be separately disclosed.

### 6. Coverage, outside audit and stopping rules

Within every frozen candidate catchment, require:

- 100% query protocol execution or a logged blocked result;
- 100% canonical candidate-specific validation attempts;
- 100% exact-observation provenance partitioning across retained/excluded branches;
- an explicit status for every candidate and review item for every possible/unresolved branch;
- exact-postal-only geocoding or a transparent branch-level unresolved outcome.

Outside the candidate set, draw a reproducible stratified audit sample after the candidate freeze and before outside discovery. The decision sheet recommends **40 non-candidate nodes**, stratified by planning region and pre-competition demand/accessibility band using a recorded random seed and retained inclusion probabilities. This is a stronger coverage check than the earlier minimum-30 proposal and permits a design-weighted H1 analysis, while remaining an audit rather than an inventory. The final size and sample-design rationale require approval before collection and cannot support a national branch total.

The audit uses the identical query, identity and validation protocol. It reports discovery yield, confirmed/possible/unresolved rates, duplicate rate, blocked rate and source limitations by stratum, without reselecting candidate nodes. Escalate for human review before ranking if the audit reveals a material, pre-specified pattern: a blocked/failed protocol stratum, an unrepresented region, or an outside-stratum confirmed-branch rate at least twice the candidate-catchment rate with at least five confirmed audit branches. This is a diagnostic escalation rule, not a statistical proof of bias.

Stop a catchment only after all its candidates have an explicit outcome. Stop the national phase and do not rank nodes if source permissions fail, a required catchment protocol cannot be run consistently, candidate coverage is incomplete, privacy controls fail, or the audit escalation condition is met without an approved response. Evidence currency follows the existing 30-day dynamic-source rule; rerun/refresh affected catchments when it expires.

### 7. Data, privacy and quality contracts

New versioned private outputs should include: `candidate_node_freeze`, `catchment_definitions`, `national_discovery_queries`, private raw observation and validation ledgers, canonical `branches`, `brands`, `branch_offerings`, `branch_catchment_membership`, `excluded_branches`, `outside_audit_sample`, `outside_audit_summary`, review queue, geocode decisions, acquisition manifest and data-quality report. Parquet is authoritative where supported; CSV is inspection-only.

Required gates include all approved pilot controls plus: candidate freeze precedes competitor evidence; every catchment links only to frozen node IDs; complete query and validation coverage within candidate and audit catchments; retained branch/catchment memberships have valid foreign keys; primary counts use confirmed/current only; possible upper-bound counts are separate; candidate and audit strata are reported; exact-observation partition, cache/attempt provenance, CSV/Parquet parity, checksums and final secret scan pass; no S010-derived evidence appears in tracked/public/app paths.

All raw discovery/validation evidence and outputs that retain it remain ignored private material. Reports expose aggregates and safe quality counts only. No credential, token, raw response, copied page text, private observation identifier or S010 content is published. A public dashboard may show only later approved aggregate/derived results with source, licence and privacy review.

### 8. Estimated workload

These are planning ranges, not evidence or a commitment:

| Activity | Proposed scale | Estimated effort |
|---|---:|---:|
| Reconstruct/freeze 146-node screening universe and QA | 146 nodes | 1–2 automated days plus 4–8 human QA hours |
| Candidate catchment construction | 30–40 nodes × primary/sensitivity bands | 1–3 automated days once routing is authorised; 4–8 human QA hours |
| Candidate discovery and validation | unique leads across overlapping catchments | roughly 150–350 unique branch candidates; 30–120 human validation hours at 12–20 minutes each, plus query logging/review |
| Outside audit | 30 nodes under the proposed minimum | roughly 40–100 additional candidate validations; 8–34 human validation hours |
| Quality review, refresh and audit interpretation | all outputs | 12–24 human hours |

Actual workload depends on query yield, duplicate rate, operator-page quality and unresolved/blocked outcomes. A lower workload is not a reason to reduce the candidate set or audit without a recorded decision.

## Connection to later analytical work

The national demand/accessibility screen supplies the inputs for the non-competitor candidate freeze. The completed catchment inventory supplies confirmed primary competition and the confirmed-plus-possible uncertainty scenario for the frozen candidates and audit sample.

H1 must not be estimated only in the high-demand/accessibility candidate subset. Its intended estimand is the eligible nationwide node universe. The recommended primary analysis combines all candidate nodes with the probability-sampled outside-audit nodes, retains stratum inclusion probabilities and uses design weights. Candidate-only results are descriptive sensitivity. Model form, spatial-dependence diagnostics, missing-coverage handling and minimum effective-sample requirements must be frozen before competitor outcomes are inspected; inadequate coverage or precision makes H1 inconclusive rather than passed. It remains observational and cannot establish causality or nationwide branch prevalence.

Only after the coverage and audit gates pass may final competition exposure enter the four-dimension Pareto comparison and five fixed weight profiles. Rankings must show the confirmed-only primary competition result, the possible-inclusive upper-bound sensitivity, unresolved/coverage flags, catchment method and audit limitations. The final dashboard may claim a comparison of the frozen, evidence-qualified candidate nodes; it may not claim national competitor completeness, national branch totals, causal market success or lease-ready premises.

## Decisions requiring user approval

No national parameter is frozen by this document. Approval is needed for:

1. Approach B rather than exhaustive 55-planning-area discovery.
2. Sequence and eligibility: second commercial signal before accessibility and candidate freeze.
3. Candidate-set selection rule, scenario(s), eligibility threshold and maximum size (decision-sheet recommendation: maximum 36).
4. Primary and sensitivity catchment thresholds/modes (proposed: 10-minute/15-minute exit-union walk; 800 m/1,200 m proximity sensitivities).
5. Final fixed query-template wording and any additional permitted discovery source.
6. Outside-audit and H1 rule (decision-sheet recommendation: 40 nodes; region × screen-band stratification; recorded seed and inclusion probabilities).
7. Workload/time budget and the escalation response if the audit identifies a material coverage concern.

Once these are approved, record the chosen values in versioned configuration and the decision log before any national acquisition begins.

## Definition of done for this phase

This design phase is complete when the approvals above are recorded, versioned configuration/contracts exist, and an implementation plan can execute the frozen protocol without further methodological choices. National competitor collection is complete only later when every frozen candidate and audit catchment satisfies its protocol and quality gates, the audit is interpreted, and all limitations are published with the resulting node comparison.
