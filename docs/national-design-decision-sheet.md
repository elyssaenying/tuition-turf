# National design decision sheet

**Status:** approved in D63 and implemented through the non-competitor candidate/audit freezes in D64, the frozen discovery protocol in D65 and the separately labelled Bukit Timah benchmark amendment in D66. The benchmark does not alter the frozen 36.

## Recommended package

| Decision | Recommended choice | Why | Main trade-off |
|---|---|---|---|
| National competitor strategy | Use the two-stage candidate-catchment design (Approach B), not an attempted 55-area census | It answers the node-location question while freezing alternatives before competitor inspection and retaining an outside audit | It cannot support a national branch total or a claim of complete Singapore coverage |
| Sequence | Qualify the node universe with a second non-competitor commercial signal; run national demand/accessibility; freeze candidates; draw the outside sample; only then inspect competitors | This closes the current zero-qualified-node gap and prevents competitor evidence from choosing the alternatives | It requires a separately authorised routing phase before the candidate set can be finalised |
| Candidate set | Balanced option: maximum 36 nodes, selected by a pre-registered demand/accessibility rule with regional coverage slots | Broad enough to preserve plausible alternatives while keeping branch validation feasible | A cap can omit weaker but locally distinctive nodes; the full screened universe must remain published |
| Competition catchment | Primary: union of 10-minute walking catchments from the preserved exits of each station complex; sensitivity: 15 minutes; 800 m and 1,200 m straight-line only as labelled proximity sensitivities/fallbacks | It measures direct rivals around the same commercial node without pretending it is the same construct as the 20-minute public-transport demand catchment | It does not measure every substitute centre reachable by a student's full journey |
| Outside audit | Balanced option: 40 non-candidate nodes, sampled with a recorded seed and stratified by planning region and pre-competition demand/accessibility band | Stronger coverage check and better support for H1 than the earlier minimum-30 proposal | Higher manual workload; still an audit rather than a national inventory |
| Discovery sources | Operator-controlled pages plus general web search as lead generation; no systematic S010 use; fixed templates and identical treatment for candidate/audit catchments | Matches the approved pilot evidence hierarchy and private/public boundary | Search-engine coverage is incomplete and changes over time |
| Workload control | Approve a 100-human-hour planning ceiling, with a mandatory re-estimate after 25% of catchments; pause rather than silently reduce coverage | Makes the portfolio feasible while keeping scope changes explicit | The full protocol may require a later owner decision to increase time or narrow claims |

The owner approved the recommended balanced package. D64 records its implementation through the 36-node candidate freeze and 40-node outside-audit freeze.

The owner's pre-existing knowledge that Bukit Timah is an established tuition hub is retained as a strategic benchmark rather than used to rewrite the pre-competition ranking. Beauty World and King Albert Park were already in the probability audit; Sixth Avenue and Tan Kah Kee are benchmark-only. All four receive the same queries and catchment rules, and their results must be compared with the frozen candidate/audit distributions before any dated amendment can be considered.

## Sequencing dependency that must be resolved

The approved node inventory contains 146 current candidates but zero formally `qualified` nodes because MP2025 zoning is only one commercial-signal family. A national candidate freeze must not quietly call all 146 evidence-qualified. The recommended sequence is:

1. Apply one legally reusable, non-competitor second commercial signal to the complete 146-node universe under a frozen rule.
2. Retain every result and reason; do not tune the signal after seeing which named nodes pass.
3. Run the separately authorised national demand/accessibility stage for nodes that meet the approved eligibility rule, retaining route failures and fallbacks.
4. Apply the frozen, non-competitor candidate-selection algorithm and checksum the complete freeze record.
5. Draw and freeze the outside-node audit sample from the non-candidate universe.
6. Begin competitor discovery only after steps 1–5 are immutable.

## Candidate-selection rule to specify before routing results are inspected

The recommended balanced structure is a maximum of 36 candidates:

- 24 merit slots selected by a deterministic equal-weight rank of accessible target-population proxy and accessibility, with stable node-ID tie-breaking;
- 12 coverage slots allocated by a predeclared planning-region × demand/accessibility-band rule, excluding duplicates already selected;
- fewer than 36 if fewer nodes satisfy the eligibility and data-quality gates;
- no competitor count, brand name, branch location, rent observation or premises listing may enter selection.

The exact region allocation and missing-route admission rule must be written into versioned configuration before the national results are calculated. A two-dimensional Pareto screen should be reported as a diagnostic, but it should not produce an uncapped, result-dependent candidate count.

## H1 correction

H1 should describe the eligible nationwide node universe, not only the deliberately high-demand candidate subset. Otherwise range restriction and selection on the explanatory variables would make the result difficult to interpret.

Recommended analysis:

- estimate the association using the candidate nodes plus the probability-sampled outside-audit nodes;
- preserve each audit stratum's inclusion probability and use design weights for the universe-level estimate;
- report an unweighted candidate-only association as descriptive sensitivity, not as the primary H1 result;
- pre-specify branch-presence and branch-count models, spatial-dependence diagnostics, missing-coverage handling and minimum effective sample requirements before competitor results are opened;
- downgrade H1 to descriptive/inconclusive if audit coverage, effective sample size or model diagnostics are inadequate.

This is still observational. It cannot show that population or accessibility causes branch placement or that branch presence demonstrates profitability.

## Construct distinction

The demand and competition catchments serve different purposes and need not use identical thresholds:

- `accessible_target_population_proxy` measures people able to reach a node under the frozen 20-minute public-transport / walking fallback design;
- primary competition counts direct rivals in the commercial-node walking catchment;
- possible branches form a separate uncertainty case, and unresolved discovery remains a coverage limitation.

The report must explain this distinction. A later secondary sensitivity may count broader transit-reachable competitors, but it must not replace the frozen primary measure after results are known.

## Workload choices

| Package | Candidate nodes | Outside audit | Expected human validation implication | Claims |
|---|---:|---:|---|---|
| Lean | 30 | 30 | Lowest feasible workload; likely near the lower end of the existing estimate | Candidate comparison plus coarse outside-coverage audit; H1 more likely descriptive/inconclusive |
| Balanced — recommended | up to 36 | 40 | Material workload, provisionally capped at 100 hours before an explicit rescope decision | Stronger candidate comparison, coverage audit and design-weighted H1 basis |
| High-rigor | All eligible nodes / exhaustive area protocol | Not applicable | Potentially several hundred validation hours and continuing refresh burden | Protocol-bound nationwide inventory claims, still not proof of completeness |

## Audit escalation

Freeze the exact rule before collection. At minimum, pause before ranking when any stratum cannot execute the protocol, a planning region is unrepresented, privacy/licensing fails, or the outside sample shows a material competitor pattern not represented in the candidate set. Do not automatically add or remove nodes after inspecting competition; any response requires a versioned design amendment and a fresh freeze.

## Owner approvals needed

The owner should approve or amend these seven items together:

1. Approach B and its limited coverage claim.
2. The sequence: second commercial signal → accessibility → candidate freeze → audit sample → competitors.
3. Balanced candidate design: maximum 36, including the merit/coverage structure.
4. Exit-union 10-minute primary walking catchment, 15-minute sensitivity and labelled proximity bands.
5. Stratified 40-node outside audit and design-weighted H1 analysis.
6. Operator-page/general-search discovery channels and fixed-template approach, with no systematic S010 use.
7. The 100-hour planning ceiling and mandatory 25% workload checkpoint.

After approval, the next implementation task is to version the second-commercial-signal source/rule and candidate/audit design configuration. It is not to collect competitor data.
