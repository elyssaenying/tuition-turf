# Project charter

## Purpose and success

Help a tuition operator planning a new physical centre decide which Singapore commercial nodes merit premises investigation for a P1–S4 mathematics offering. The operator may be opening its first centre or expanding; the latter requires an explicit existing-network scenario. Success means a reproducible, defensible shortlist with quantified feasibility and visible uncertainty, not a claim that demographic concentration guarantees demand or profit.

The delivered analytical output is a shortlist of up to three evidenced commercial nodes with scenario-specific trade-offs, explicit rent assumptions, break-even requirements, Pareto comparisons and robustness results. A conditional node may be recommended from population proxy, accessibility, competition and financial scenarios without a current premises record. Use a generic `operator_assumption` occupancy-cost grid, state every assumed rent value and test sensitivity; S016 remains restricted manual context and cannot generate published node-specific rent ranges. Specific-premises evidence is optional later due diligence. A current unit may be described as lease-ready only with the required unit evidence; `verified_eligible` covers the defined premises-use, owner-consent and fire-safety checks only and is not proof that school/operator-registration or commercial/lease requirements are complete. If fewer than three nodes qualify, report the shortfall and evidence gaps; never force three recommendations.

## Decision units and geographic levels

| Level | Unit and role | Guardrail |
|---|---|---|
| National screening | All Singapore planning areas using a compatible published boundary vintage | Include low-coverage areas with flags; no silent geographic omissions |
| Demand allocation | Smallest reliable resident age-by-area geography, provisionally subzones | Do not imply subzone precision if only planning-area counts exist |
| Candidate comparison | A defined commercial node with stable ID, boundary/anchor and accessible catchment | A node is neither an entire planning area nor an arbitrary map pin |
| Node financial scenario | Node × explicit rent and operating assumptions | Use a generic `operator_assumption` grid; state rent values and sensitivity, with no claim that they are observed node or unit rents |
| Optional premises evidence and cost | A specific physical premises/unit associated with a node | Public screening may support `screened_feasible`; unit-specific authoritative evidence is required for `verified_eligible` |
| Recommendation | Node × operating scenario | Conditional node recommendations may use transparent rent assumptions; lease-ready unit claims need current availability, quoted rent, permitted use, owner consent and applicable URA/SCDF evidence, while operator/school and commercial/lease checks remain separate |

Node definitions will be frozen before final model outputs are inspected. Boundaries, anchor selection, catchment rules and cross-boundary allocation must be reproducible. Population, competitors and schools can fall outside a node boundary while still being inside its accessible catchment.

## Inclusion and exclusion

Include Singapore resident children approximately aged 7–16, commercial nodes plausibly capable of hosting P1–S4 mathematics under explicit assumptions, and operating competitor branches confirmed to provide overlapping mathematics levels. Include independent operators and chain branches under the same rules. Include relevant education providers separately when examining cluster effects. Add specific physical premises only in the optional due-diligence layer.

Exclude online-only providers, private tutors without an identifiable public teaching branch, closed branches at the analysis cut-off, and offerings confirmed to be outside the subject/level scope from direct competitor counts. Retain uncertain, planned, relocated and out-of-scope records with explicit statuses for audit or scenario use. Schools indicate activity/access context; school enrolment must not be added to resident counts as another population pool. Assign premises `ineligible` after a confirmed mandatory premises failure and `unresolved` when premises evidence is insufficient or contradictory. Public evidence revealing no known premises blocker supports only `screened_feasible`, while `verified_eligible` requires unit-specific authoritative confirmation of all defined mandatory premises requirements.

Resident ages 7–16 inclusive are a proxy for P1–S4, subject to entry timing and student progression. Secondary 5 is outside the subject/level scope, although the age proxy can overlap S5 pupils; age therefore cannot establish school level. Non-resident pupils, cross-area travel, enrolment choices and willingness to pay are not measured by resident population. Coarse age groups need a labelled approximation and alternative bounds; they must not be relabelled as exact counts. Primary 1 balloting is not a core input.

## Evidence and interpretation

Every observation needs a source, date and unit. Every calculation needs lineage and a method version. Proxies require an explanation; assumptions require an owner/review status and sensitivity range. H1 and the wider analysis are observational and cannot establish that population causes branch formation, that clusters cause demand, that a resident will enrol, or that a particular node will outperform a counterfactual location. Existing branch placement is evidence of revealed location behaviour, not proof that the branch is successful. Education-cluster effects remain optional and exploratory unless sufficient evidence supports a confirmatory test.

No numerical rent, fee, conversion, utilisation, wage, class-size or travel-time baseline is accepted in this pass. Values will be evidence-backed or explicitly provisional and reviewed. The five ranking weight profiles are design rules, not empirical baselines. S016 street-level retail rental statistics are restricted manual context and cannot be stored or reproduced in public portfolio outputs; they do not support node-specific analytical rent ranges. Every conditional node recommendation must state its generic `operator_assumption` rent grid and show sensitivity across rent values. Use SGD and monthly recurring quantities in the financial model, with annual/term amounts converted using documented rules.

## Constraints and major risks

- Age/geographic resolution, vintages and boundary changes may prevent fine-grained comparisons.
- Branch listings may be stale, incomplete or inconsistent about subjects, levels and operating status.
- Straight-line distance may overstate accessibility across barriers; travel times may vary by schedule and mode.
- Generic occupancy-cost assumptions are not observed market rents; current availability, quoted all-in cost and premises permission remain unverified until optional due diligence.
- URA/SCDF premises checks do not establish whether Education Act/MOE school or operator registration and ordinary lease/commercial requirements apply or have been satisfied.
- Population, affordability proxies and school proximity do not reveal actual take-up or willingness to pay.
- Expansion cannibalisation is an optional conditional analysis requiring operator data; it is not a core hypothesis or a prerequisite for the general commercial-node shortlist.
- Catchments overlap; sparse evidence and related demand variables can create false precision or double counting.
- Licence restrictions may limit redistribution; addresses must concern public businesses, not private pupil records.

## Scope boundary after source feasibility

Source pages, metadata, access conditions and contracts were validated on 2026-09-12. Foundational run `foundation_7dbd9a143e9504e7` then fully processed S001 and acquired/processed the approved S003–S006 nationwide snapshots. The S001–S003 crosswalk matched all 332 subzones exactly; validated school and transport-context tables are available with documented exceptions. S007 remains limited: walk succeeded for 30/30 fixed pairs, PT for 19/30, and 11 PT routes were explicitly missing with no rate limiting. Missing PT routes require the documented walking/proximity fallback and are not imputed. Competitor acquisition, national routing, node scoring, analysis and dashboard implementation remain deferred. The absence of current-unit availability, quoted rent and unit-specific eligibility evidence blocks only unit-level or lease-ready conclusions, not conditional commercial-node shortlisting under explicit operator assumptions. The core release comprises national planning-area screening, reproducible nodes, the preferred 2025 age source or documented fallback, route-specific OneMap results with honest fallback, nationwide competitor discovery with stated coverage limits, complete manual validation of branches affecting shortlisted catchments, transparent financial/inverse-break-even scenarios, Pareto/weight sensitivity, an analytical report and a static dashboard. See the [source-feasibility matrix](source-feasibility-matrix.md) for exact verdicts and the [definition of done](definition-of-done.md) for later acceptance gates.
