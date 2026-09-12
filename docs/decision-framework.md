# Decision framework

## Eligibility before comparison

1. Screen every planning area with compatible data, recording missingness and proxy quality.
2. Define commercial nodes with documented selection rules. Preserve screened-out areas and reasons. Use multiple screening signals and coverage review so a single proxy does not eliminate promising areas without explanation.
3. Investigate premises within candidate nodes. Record intended tuition use, public evidence, unit-specific authoritative evidence where obtainable, usable teaching space, practical access, operating constraints and all-in occupancy cost. Do not infer permission from an education neighbour or a listing category.
4. Assign each premises exactly one status: `verified_eligible`, `screened_feasible`, `ineligible` or `unresolved`. `verified_eligible` requires unit-specific authoritative evidence confirming every defined mandatory requirement. `screened_feasible` means currently available public evidence reveals no known blocker, while final permission or landlord confirmation remains. `ineligible` means at least one confirmed mandatory failure. `unresolved` means the evidence is insufficient or contradictory.
5. Run scenario comparisons for node/premises combinations supported by `verified_eligible` or `screened_feasible` premises and an evidenced cost scenario. A `screened_feasible` premises can support a conditional commercial-node shortlist only when the remaining confirmation is explicit. A fully recommended or lease-ready premises requires `verified_eligible`. Premises that are `unresolved` remain investigation leads, and `ineligible` premises leave the comparison pool.

The definitive list of mandatory premises checks and evidence authorities must be established from directly verified official requirements during source feasibility. Additional operator constraints require recorded agreement. This scaffold does not assert current legal or planning requirements.

## Hypotheses recorded before results

| ID | Testable expectation | Planned comparison and possible challenge |
|---|---|---|
| H1 | Commercial-node catchments with larger accessible resident populations aged approximately 7–16 tend to contain more confirmed P1–S4 mathematics tuition branches. | Test the association using the frozen catchment and branch definitions, with sensitivity to age allocation, catchment specification and uncertain branch coverage. This is observational and does not establish causality. |
| H2 | A shortlist based only on target population changes materially after competition, occupancy cost and premises feasibility are incorporated. | Compare the population-only shortlist with the full decision shortlist. Define the shortlist size, comparison metric and numerical threshold for “materially different” before final results are inspected. |
| H3 | Transit-aware accessibility produces materially different catchment demand estimates or candidate ordering from straight-line proximity. | Compare demand estimates and ordering under frozen transit-aware and straight-line methods. Define numerical materiality thresholds before final results are inspected. |
| H4 | At least one shortlisted candidate remains non-dominated across at least 70% of the explicitly defined plausible scenario grid. | Calculate each candidate's non-dominated scenario share over the complete, versioned grid. The 70% threshold is a robustness criterion over that grid, not a probability of business success. |

These are pre-results expectations, not findings. Record the numerical definitions of “materially different” and the complete plausible scenario grid before final results are inspected. Use descriptive contrasts and uncertainty analysis. H1 is observational; any statistical association must account for small samples, confounding and spatial dependence and cannot establish causality. Education-cluster effects are exploratory unless sufficient evidence supports a separate confirmatory test. Expansion cannibalisation is an optional conditional analysis when authorised operator data is available, not a core hypothesis.

## Pareto comparison

Compare admissible alternatives supported by `verified_eligible` or `screened_feasible` premises within the same scenario, data cut-off and coverage standard. An alternative dominates another when it is at least as good on every selected criterion and strictly better on at least one. Publish criterion definitions, direction, any practical-equivalence tolerance and the full comparison set. Preserve premises status in every comparison. Do not treat missing values as zero, best, worst or a passing result; incomplete alternatives get `insufficient_data`.

| Criterion | Direction | Planned measurement |
|---|---|---|
| Accessible target population | Maximise | Unique resident age-proxy population covered by the stated catchment method |
| Transit accessibility | Maximise | Share of relevant resident population reachable within a documented transit-time threshold |
| Direct competition exposure | Minimise | Confirmed and possible overlapping mathematics branches within the relevant catchment, preferably adjusted for distance and P1–S4 level overlap if supported by available data; exact formulation deferred until source feasibility |
| Break-even burden | Minimise | Break-even active enrolments divided by practical enrolment capacity |
| Downside financial exposure | Minimise | Peak cumulative cash deficit under an agreed adverse ramp-up scenario |

Show confirmed and possible branch counts alongside the exposure measure, method and quality flags. Branches per 1,000 target residents remains a descriptive diagnostic only, because target population is already a separate Pareto dimension; it is not the primary competition criterion. The factor of 1,000 is a reporting scale, not an operating assumption, and a zero or unknown population denominator yields a null diagnostic and a flag. Criteria and scenario ranges are provisional (D06, D22); review correlated population/access measures to avoid counting the same advantage twice. Education-cluster measures remain exploratory and separately visible unless sufficient evidence supports a confirmatory test. Do not subtract an assumed cluster benefit from competitor counts.

Pareto membership is not an overall ranking and can include many alternatives. Explain remaining trade-offs with operator constraints, evidence quality, robustness and a documented selection rationale. If optional preference weights are later used, display the weights, their provenance and alternative-weight outcomes; do not label the result objectively best. Evidence completeness is a publication gate and annotation, not an unexamined substitute for business merit.

## Recommendation format

Each shortlisted node must show its supporting premises and premises status; public and unit-specific evidence; any remaining permission or landlord confirmation; catchment and age-proxy method; confirmed and possible branch counts; competition exposure, method and quality flags; branches per 1,000 as a diagnostic; exploratory cluster context; financial assumptions and break-even/capacity results; scenario-specific Pareto status; non-dominated scenario share; adverse outcomes; unresolved risks; and a next due-diligence action. Label nodes backed by `screened_feasible` premises as conditional and never lease-ready. A fully recommended or lease-ready premises requires `verified_eligible`. Do not imply three simultaneous openings are optimal: joint expansion needs overlap-adjusted demand and optional network analysis.
