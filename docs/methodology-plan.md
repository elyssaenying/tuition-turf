# Methodology plan

## 1. Verify source feasibility and freeze the analysis design

Open source pages directly and register exact resource identifiers, access dates, coverage, licensing and relevant fields before acquisition. Confirm whether compatible age, boundary, transport and branch information exists. Select an analysis cut-off and acceptable source-age policy based on actual update frequency. Before final results are inspected, define numerical materiality for H2 and H3, define the complete plausible scenario grid for H4, and freeze node-selection and primary catchment rules. Log later deviations from the four pre-results hypotheses. No sources or numerical scenario baselines are verified in this pass.

## 2. Acquire and harmonise later

Preserve acquired snapshots without in-place editing; record source/retrieval dates, checksums, extraction parameters, schema and transformation versions. Keep raw observations separate from resolved entities. Produce compatible planning-area and, where supported, subzone tables. Treat boundary changes as explicit crosswalks; validate population conservation and flag approximate allocation. Express coordinates in WGS84 for exchange; select and verify a suitable metre-based Singapore projection for distance/area calculations before implementing them. Publish CRS and boundary versions rather than calculating metres from degrees.

## 3. Define the target-population proxy

The intended interval is resident ages 7–16 inclusive. Prefer single-year counts. If only grouped ages 5–9, 10–14 and 15–19 are available, a provisional uniform-within-band approximation is:

`target_proxy = (3/5 × residents_5_9) + residents_10_14 + (2/5 × residents_15_19)`.

The fractions select ages 7–9 and 15–16; they are allocation assumptions, not observed age distributions. Preserve the original groups. A conservative identification interval with only these groups is `[residents_10_14, residents_5_9 + residents_10_14 + residents_15_19]`; it is broad by design, not a confidence interval. Later use supported age profiles for tighter scenarios if available, without claiming local precision from national profiles. Recompute using ages 6–15 and 8–17 where feasible to test cohort alignment. For grouped inputs these shifted ranges can yield identical estimates under uniform allocation; report that lack of discriminatory information.

Allocate to catchments using the smallest reliable source geography. Area-weighted allocation assumes uniform residential density and must be labelled accordingly; residential-weighted allocation requires independently supported residential weights. Preserve population totals within tolerance. Avoid distributing residents over industrial/open land without acknowledging the approximation. Do not sum overlapping catchment populations into a national or multi-centre total.

## 4. Screen nationally, then define nodes and access

Produce a coverage-aware planning-area comparison of age-proxy demand, branch presence, transport context and premises-market evidence. Retain the full national comparison and exclusion log. Agree a manageable candidate set only after coverage review; do not set a numerical top-k cut-off in this pass.

Define each node's commercial boundary and representative access anchor using source evidence and an explicit rule. Develop walking/public-transport catchments with stated modes, journey dates/time windows, transfer assumptions and thresholds. Test multiple plausible thresholds after source feasibility; do not invent baseline minutes now. If routing is infeasible, use labelled straight-line proximity as a weaker proxy and change output names/status accordingly. Missing travel-time data must not populate a transit-reach field as though verified. Document cross-node catchment overlap and test anchor placement effects.

## 5. Resolve and validate competitor branches

Maintain separate brands, physical branches and branch offerings. One branch is one operator's identifiable, operating teaching location at a specific address/unit at the analysis cut-off. The same branch offering several levels is counted once; different chain locations count separately. Independent operators get separate brand identities. Two operators at one building are not automatically duplicates. A relocation is a new physical branch record linked to the old one; only the operating site counts at a given cut-off. Retain aliases and source records for audit.

For every shortlisted catchment, validate address/unit, operating status, mathematics provision, overlapping P1–S4 levels and source date. Prefer an operator's official branch/course evidence, corroborated where possible by an independent public listing or documented field check. Do not infer levels from a brand's generic description when branch availability is unknown. Conflicts need manual resolution or `uncertain` status; a map listing alone is not proof of subject overlap. Record geocode candidates, match quality and adjudication rather than accepting the first result. No outreach is authorised in this pass.

Publish confirmed in-scope branch counts and possible additional branch counts. Construct a provisional direct competition exposure from confirmed and possible branches within each relevant catchment, preferably adjusted for distance and P1–S4 level overlap if the data support it. Defer the precise formulation until source feasibility and publish the method and quality flags with every exposure value. Retain branches per 1,000 target residents as a descriptive diagnostic alongside absolute and exposure measures, not as the primary Pareto competition criterion. Test duplicate/closed/planned branches, boundary effects and unobserved coverage. A branch is not equivalent to seats or market share; unavailable capacity remains unknown. Count other education-provider branches separately; keep direct mathematics rivals out of a claimed complementary-provider measure to avoid using the same record as both competition and an assumed benefit. Treat education-cluster effects as exploratory unless sufficient evidence supports a separate confirmatory test.

## 6. Check premises eligibility

For each candidate premises, maintain a checklist with pass/fail/unknown outcomes, evidence, review dates and expiry where applicable. Record listing availability independently of permission and separate public screening evidence from final unit-specific legal or landlord confirmation. Assign exactly one premises status: `verified_eligible` when unit-specific authoritative evidence confirms every defined mandatory requirement; `screened_feasible` when currently available public evidence reveals no known blocker but final permission or landlord confirmation remains; `ineligible` when at least one mandatory requirement has a confirmed failure; or `unresolved` when evidence is insufficient or contradictory.

A premises with `screened_feasible` status and an evidenced cost scenario can support a conditional commercial-node shortlist, provided every remaining confirmation is explicit. It is not lease-ready. A fully recommended or lease-ready premises requires `verified_eligible`. Premises that are `ineligible` leave the comparison pool; `unresolved` premises remain investigation leads. Reconfirm evidence before any lease decision. No current regulatory requirements are asserted by this plan.

## 7. Model operating break-even and cash needs

All monetary inputs use SGD; recurring inputs are per month unless an explicit conversion is stored. Baselines remain unset. Define `N` as active unique students purchasing one recurring mathematics place each. If multiple products or levels have different economics, later model segments explicitly and reconcile segment enrolments to unique pupils; do not silently mix seats, lessons and students.

| Variable | Meaning | Evidence/review requirement |
|---|---|---|
| `p` | Effective monthly recurring fee per student, after discounts/refunds | Fee schedules and a documented collection/discount policy |
| `v` | Variable cost per student-month, excluding separately modelled class costs | Materials, transaction charges and relevant variable services |
| `F` | Monthly fixed operating costs | All-in recurring rent/charges, baseline payroll, utilities, insurance, software, administration, owner compensation and recurring marketing as applicable |
| `C` | Feasible active-student capacity | Rooms, timetable, class size, levels, teacher availability and a consistent enrolment unit |
| `b`, `k` | Students per additional class and monthly cost per class, when relevant | Timetable/staffing evidence; no default class size or wage |
| `K` | One-time opening expenditure | Fit-out, furniture, equipment and launch costs; avoid duplicate monthly allocation |
| `D` | Recoverable deposit and other tied-up working capital | Lease/payment evidence; a cash requirement rather than recurring expense |
| `N_t` | Enrolment path by month | Participation, capture, ramp-up, churn and retention assumptions with scenario bounds |
| `A`, `q`, `s` | Addressable resident proxy, tuition participation and operator capture fractions | `A` is a proxy; `q` and `s` need evidence or explicit assumptions; `A × q × s` is a scenario, not forecast truth |

For the simple linear case, contribution per student is `m = p - v` and monthly operating surplus is `N × m - F`. If `m > 0`, `N_BE = ceil(F / m)` and break-even utilisation is `N_BE / C` for positive `C`. Values above 1 mean capacity cannot support break-even. If `m <= 0` and `F > 0`, no finite break-even exists. Handle zero fixed costs by evaluating the nonnegative-surplus condition directly; do not emit invalid infinity/NaN values or imply a viable business with no contribution.

Class-based tutor costs are usually discontinuous: for a justified single-segment illustration of the planned method, surplus is `N × (p - v) - F - k × ceil(N / b)`. Where this model is adopted, keep `k` out of `F` and `v`. Search feasible integer enrolments within `C` for the first nonnegative surplus, and inspect the entire range because opening another class can reduce surplus again. A real multi-level timetable must use its feasible class allocation rather than assume all students can share a class. Store the model type and return `capacity_infeasible` if no feasible enrolment works. Report staffing-cost alternatives instead of relying on the simple formula when its assumptions fail.

Capacity must be reconstructed from actual timetable assumptions: teaching spaces × usable lesson slots × seats per class, divided by required slots per student, with level mix and staffing constraints. Seat-slots and unique students are not interchangeable. The planning baseline is one recurring place per student; additional weekly sessions reduce available enrolment capacity unless supported by additional slots.

Keep operating break-even distinct from cash payback. Model opening outflows `K + D`, monthly collected revenue and cash payments with payment timing, and cumulative cash balances. State treatment of deposits, advance fees, refunds, tax, financing and owner pay. Report maximum cash deficit before funding as working-capital need and first sustained recovery of opening cash outflows as payback, if reached within the stated horizon. Recoverable deposits return only under an explicit scenario. Do not invent a payback horizon or assume tax treatment; verify relevant treatment when implementation requires it.

Expansion cannibalisation is an optional conditional analysis, not a core hypothesis. When authorised existing-network evidence is available, measure net incremental network cash flow, including cannibalised contribution and shared-cost changes. Otherwise report stand-alone results without making the general shortlist depend on private operator data.

## 8. Compare alternatives and expose uncertainty

Build scenario-specific Pareto frontiers using the decision-framework criteria. Admit alternatives supported by `verified_eligible` or `screened_feasible` premises and preserve that status in the results; keep `ineligible`, `unresolved` and incomplete-data alternatives outside dominance calculations. State whether cost criteria compare a nominated premises, a premises range or an evidenced subset; do not pick only a node's cheapest unsupported listing. Use direct competition exposure as the primary competition criterion, with its precise formula deferred until source feasibility. Keep branches per 1,000 target residents descriptive.

Planned tests include age-band allocation and cohort shifts; geography/boundary vintages; area versus residential weighting; catchment modes, thresholds and anchors; competitor omissions/duplicates/status, distance treatment and level overlap; exploratory cluster measures; asking versus all-in rent; fees/discounts, variable costs, class costs, capacity and utilisation; ramp-up/churn, participation and capture; fit-out/deposits; and optional expansion cannibalisation. Start with one-way sensitivities and a coherent, explicit plausible scenario grid. Avoid impossible combinations and independently sampling related parameters without justification.

Use interval bounds where probability distributions lack evidence. Monte Carlo is optional only after defensible distributions/dependencies are recorded, with seed and draws for reproducibility. Report feasibility changes, break-even ranges, Pareto-membership frequency over the explicit scenario grid and shortlist turnover. Test H4 by determining whether at least one shortlisted candidate is non-dominated in at least 70% of that grid. This frequency and threshold are robustness criteria over the defined grid, not probabilities of business success. Report rank changes only if an explicit preference ranking has been introduced. Hold out final recommendation selection until these checks are complete.

## 9. Export and communicate

Publish a validated, versioned static bundle under the data contracts. The dashboard should support node/premises comparison, scenario selection, source inspection and explanation of trade-offs. Include coverage, cut-off dates, proxy labels, eligibility uncertainty and limits beside the relevant measures. Keep large raw data, personal information and credentials out of browser assets. Analysis text and figures belong in `reports/`; no such outputs exist yet.
