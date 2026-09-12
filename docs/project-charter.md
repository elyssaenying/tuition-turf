# Project charter

## Purpose and success

Help a tuition operator planning a new physical centre decide which Singapore commercial nodes merit premises investigation for a P1–S4 mathematics offering. The operator may be opening its first centre or expanding; the latter requires an explicit existing-network scenario. Success means a reproducible, defensible shortlist with quantified feasibility and visible uncertainty, not a claim that demographic concentration guarantees demand or profit.

The eventual deliverable is a shortlist of up to three evidenced commercial nodes with scenario-specific trade-offs, a premises evidence trail, break-even requirements, Pareto comparisons and robustness results. A node may enter a conditional shortlist when at least one premises is `screened_feasible` and has an evidenced cost scenario; the remaining permission or landlord confirmation must be named, and the node must not be described as lease-ready. A fully recommended or lease-ready premises requires `verified_eligible` status. If fewer than three nodes qualify at either strength, report the shortfall and evidence gaps; never force three recommendations. Nodes supported only by `unresolved` premises remain investigation leads.

## Decision units and geographic levels

| Level | Unit and role | Guardrail |
|---|---|---|
| National screening | All Singapore planning areas using a compatible published boundary vintage | Include low-coverage areas with flags; no silent geographic omissions |
| Demand allocation | Smallest reliable resident age-by-area geography, provisionally subzones | Do not imply subzone precision if only planning-area counts exist |
| Candidate comparison | A defined commercial node with stable ID, boundary/anchor and accessible catchment | A node is neither an entire planning area nor an arbitrary map pin |
| Premises evidence and cost | A specific physical premises/unit associated with a node | Public screening may support `screened_feasible`; unit-specific authoritative evidence is required for `verified_eligible` |
| Recommendation | Node × operator scenario, supported by an evidenced premises scenario | `screened_feasible` can support a conditional node shortlist; lease-ready claims require `verified_eligible` |

Node definitions will be frozen before final model outputs are inspected. Boundaries, anchor selection, catchment rules and cross-boundary allocation must be reproducible. Population, competitors and schools can fall outside a node boundary while still being inside its accessible catchment.

## Inclusion and exclusion

Include Singapore resident children approximately aged 7–16, physical premises capable of serving P1–S4 mathematics, and operating competitor branches confirmed to provide overlapping mathematics levels. Include independent operators and chain branches under the same rules. Include relevant education providers separately when examining cluster effects.

Exclude online-only providers, private tutors without an identifiable public teaching branch, closed branches at the analysis cut-off, and offerings confirmed to be outside the subject/level scope from direct competitor counts. Retain uncertain, planned, relocated and out-of-scope records with explicit statuses for audit or scenario use. Schools indicate activity/access context; school enrolment must not be added to resident counts as another population pool. Assign premises `ineligible` after a confirmed mandatory failure and `unresolved` when evidence is insufficient or contradictory. Public evidence revealing no known blocker supports only `screened_feasible`, while `verified_eligible` requires unit-specific authoritative confirmation of all defined mandatory requirements.

Resident ages 7–16 inclusive are a proxy for P1–S4, subject to entry timing and student progression. Non-resident pupils, cross-area travel, enrolment choices and willingness to pay are not measured by resident population. Coarse age groups need a labelled approximation and alternative bounds; they must not be relabelled as exact counts.

## Evidence and interpretation

Every observation needs a source, date and unit. Every calculation needs lineage and a method version. Proxies require an explanation; assumptions require an owner/review status and sensitivity range. H1 and the wider analysis are observational and cannot establish that population causes branch formation, that clusters cause demand, that a resident will enrol, or that a particular node will outperform a counterfactual location. Education-cluster effects remain exploratory unless sufficient evidence supports a confirmatory test.

No numerical rent, fee, conversion, utilisation, wage, class-size, travel-time or scoring-weight baseline is accepted in this pass. Values will be evidence-backed or explicitly provisional and reviewed. Use SGD and monthly recurring quantities in the financial model, with annual/term amounts converted using documented rules.

## Constraints and major risks

- Age/geographic resolution, vintages and boundary changes may prevent fine-grained comparisons.
- Branch listings may be stale, incomplete or inconsistent about subjects, levels and operating status.
- Straight-line distance may overstate accessibility across barriers; travel times may vary by schedule and mode.
- Asking rents can differ from attainable all-in occupancy costs; premises permission can remain unverified.
- Population, affordability proxies and school proximity do not reveal actual take-up or willingness to pay.
- Expansion cannibalisation is an optional conditional analysis requiring operator data; it is not a core hypothesis or a prerequisite for the general commercial-node shortlist.
- Catchments overlap; sparse evidence and related demand variables can create false precision or double counting.
- Licence restrictions may limit redistribution; addresses must concern public businesses, not private pupil records.

## Scope boundary for this pass

Deliver documentation and empty directories only. Acquisition, source-page verification, dependencies, executable pipelines, fixtures, analysis, dashboard implementation and results are deferred. All source leads are unverified. See the [definition of done](definition-of-done.md) for later acceptance gates.
