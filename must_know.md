# Must-know project guide

This is the short presentation guide for the project. It should be updated after every major analysis stage so the work can be explained clearly without reading the whole codebase.

## Project question

Which Singapore MRT areas look most promising for a physical P1–S4 mathematics tuition centre?

The project starts with all **146 current MRT-area candidates** and compares them in stages:

1. nearby school-age population;
2. real public-transport and walking accessibility;
3. nearby mathematics-tuition competition;
4. financial feasibility under stated assumptions; and
5. robustness checks before recommending up to three areas.

The final release recommends **Sengkang and Serangoon**. It deliberately reports only two areas because Yishun and Bukit Panjang do not survive the conservative zero-confirmed competition stress test.

## Major part 1 — population proximity analysis (complete)

### What question did it answer?

For each of the 146 MRT areas, approximately how many residents aged 7–16 live geographically nearby?

This was a first screening measure. It did **not** measure actual travel time, tuition demand, enrolment, or business success.

### Was it done using code?

Yes. Python code performed the same calculation for every MRT area. The main files are:

- `src/tuition_location_analytics/analysis/proximity.py`
- `src/tuition_location_analytics/analysis/proximity_cli.py`
- `config/analysis/proximity_baseline.json`

The main idea in the code was:

```python
# Draw a radius around every exit and merge overlapping areas.
catchment = unary_union([
    exit_point.buffer(radius_metres)
    for exit_point in station_exits
])

# Give the catchment a share of each subzone's population
# according to the share of the subzone area that overlaps it.
share = overlap_area / subzone_area
estimated_nearby_population += subzone_population * share
```

The actual code also checks for invalid or empty areas, caps the share between 0 and 1, counts nearby schools and bus stops, creates ranks, and runs quality checks.

### What data was used?

| Data | Source | How it was used |
|---|---|---|
| Residents aged 7–16 in 332 subzones | [Singapore Department of Statistics, Population Trends 2025](https://www.singstat.gov.sg/publication-resources/population-trends-2025) | Added ages 7–16 to form the target-age population proxy for each subzone |
| Subzone boundary shapes | [URA MP2019 Subzone Boundary from data.gov.sg](https://data.gov.sg/datasets/d_8594ae9ff96d0c708bc2af633048edfb/view) | Provided the map areas used to allocate population |
| 613 MRT/LRT exits | [LTA MRT Station Exit from data.gov.sg](https://data.gov.sg/datasets/d_b39d3a0871985372d7e1637193335da5/view) | Created the nearby area around every exit in each station complex |
| 5,205 bus stops | [LTA Bus Stop from data.gov.sg](https://data.gov.sg/datasets/d_3f172c6feb3f4f92a2f47d93eed2908a/view) | Counted as transport context only |
| 337 schools | [MOE General Information of Schools from data.gov.sg](https://data.gov.sg/datasets/d_688b934f82c1059ed0a6993d2a829089/view) | Counted as education context only; 330 had usable coordinates and 7 unresolved schools were omitted from spatial counts |

Exact source links, retrieval dates, checksums, and limitations are recorded in `docs/source-register.md`.

### How was the number derived?

1. The code grouped MRT exits into 146 MRT areas.
2. It converted all map data to Singapore's metre-based coordinate system, EPSG:3414.
3. It drew an **800 m straight-line radius around every exit** and merged overlapping exit areas for the same MRT area.
4. It repeated the calculation at **1,200 m** as a sensitivity check.
5. When only part of a population subzone overlapped the MRT area, it assigned the same fraction of that subzone's ages 7–16 population.
6. It ranked the 146 MRT areas by the resulting 800 m population proxy.

Simple example: if 25% of a subzone's map area falls inside the MRT catchment and the subzone has 4,000 residents aged 7–16, the method assigns about 1,000 of them to that catchment.

### Why use every station exit?

A large interchange may have exits spread across a wider area. Drawing the catchment around every preserved exit better represents the area people can enter or leave the station than drawing one circle around the station's centre point.

### What were the first results?

The five highest 800 m population-proxy values were:

| Rank | MRT area | Estimated ages 7–16 population nearby |
|---:|---|---:|
| 1 | Sengkang | 10,084 |
| 2 | Punggol | 9,214 |
| 3 | Admiralty | 8,954 |
| 4 | Buangkok | 7,012 |
| 5 | Tampines | 6,681 |

These are **early population-proximity results**, not the best business locations and not the final shortlist.

### Important assumptions and limitations

- The method assumes people are spread evenly inside each subzone because more detailed residential locations were unavailable. In reality, some land contains parks, industry, roads, or concentrated housing.
- The circles use straight-line distance, not the walking path around roads, buildings, crossings, or barriers.
- A resident inside the circle is not automatically a tuition customer.
- Catchments from different MRT areas overlap, so their values must not be added together.
- Bus-stop and school counts are context, not proof of accessibility or demand.
- Published small-area population counts are rounded, so the result is an estimate rather than an exact headcount.

### Quality checks

- All 146 MRT areas were processed.
- Every MRT area had at least one station exit.
- No duplicate MRT-area identifier was found.
- No negative or impossible population value was produced.
- Every 1,200 m result was at least as large as its 800 m result.
- The calculation was saved to CSV and Parquet with an immutable run ID: `proximity_baseline_965a36240409d092`.

### How to explain it in a portfolio presentation

> I first created a consistent national baseline for all 146 MRT areas. Using Python spatial-analysis code, I drew 800 m catchments around all exits in each station complex. I then estimated the ages 7–16 population inside each catchment by allocating each subzone's population according to its overlapping area. I repeated the analysis at 1,200 m to test sensitivity. I treated these results only as an early proximity proxy, because straight-line distance and evenly distributed population are simplifying assumptions. The next stage tests actual public-transport and walking accessibility before any shortlist is made.

### Where are the outputs?

- `data/processed/analysis/2026-09-17/proximity_baseline_965a36240409d092/`
- `reports/analysis/2026-09-17/proximity_baseline_965a36240409d092/analysis-summary.md`
- `reports/analysis/2026-09-17/proximity_baseline_965a36240409d092/top-20-population-proxy.svg`

## Major part 2 — real travel accessibility (complete)

### What question did it answer?

Can the target-age population realistically reach each MRT area by public transport and walking at the selected journey times?

The purpose is **not** to check whether an MRT area has public transport—it obviously does. The purpose is to estimate how many school-age residents can reach that MRT area conveniently.

Each planned journey starts at the centre point of one residential subzone and ends at the closest preserved exit of the candidate MRT area. The public-transport route may use buses, MRT, or both. Starting at the resident's nearest MRT would incorrectly ignore the first part of the journey from home to that station.

The main accessibility rule is a journey of **20 minutes or less**. The analysis will also check 15 minutes as a stricter case and 25 minutes as a more generous case. A 40-minute journey with multiple transfers therefore does not count as the main target audience.

The completed run covers **332 subzone starting points × 146 MRT areas × two frozen times = 96,944 public-transport requests**, plus 3,969 required walking fallbacks. The main weekday result counts the ages 7–16 population represented by subzone centroids that can reach each MRT area within 20 minutes by public transport, or within 10 minutes using the documented walking fallback.

### Was it done using code?

Yes. Python generated every origin–destination request, cached only safe outcomes, applied the same fallback rules, summed accessible population, created ranks, and compared the result with the straight-line baseline.

Main files:

- `src/tuition_location_analytics/analysis/routing_plan_cli.py`
- `src/tuition_location_analytics/analysis/routing_execute.py`
- `src/tuition_location_analytics/analysis/accessibility_aggregate.py`
- `src/tuition_location_analytics/analysis/accessibility_aggregate_cli.py`

Core idea:

```python
if pt_route_is_within_20_minutes:
    pt_population += origin_population
elif pt_result_is_unavailable and walk_route_is_within_10_minutes:
    walking_population += origin_population
elif pt_and_walk_are_unavailable and straight_line_distance <= 800:
    proximity_fallback_population += origin_population

accessible_population = pt_population + walking_population + proximity_fallback_population
```

The output keeps those three contributions separate. The proximity fallback is never presented as a measured travel time.

### Walking setting decision and bounded test

[OneMap](https://www.onemap.gov.sg/apidocs/routing) calls `maxWalkDistance` the maximum walking distance for a public-transport route, but its public documentation does not explain in enough detail whether this is accumulated across all walking parts or applied another way internally. We should not claim more precision than the documentation provides.

- **300 m:** roughly 4–5 minutes for an average adult; strict comparison.
- **500 m:** roughly 6–8 minutes for an average adult; approved main setting.
- **1,000 m:** roughly 12–15 minutes for an average adult; generous comparison only.

The owner approved 500 m as the main setting before any national accessibility result was inspected. Run `walk_comparison_11ab30dda2b46b67` then tested the same 20 automatically selected residential-area-to-MRT pairs at all three walking limits. The sample was balanced across four straight-line distance bands and used the weekday after-school scenario.

| Maximum walking | Successful PT routes | Missing PT routes | Reached within 20 minutes | Median successful PT time |
|---:|---:|---:|---:|---:|
| 300 m | 19 | 1 | 4 | 32.17 min |
| 500 m | 19 | 1 | 4 | 32.17 min |
| 1,000 m | 19 | 1 | 4 | 32.17 min |

All 20 pairs had the same route status and duration under all three settings. This does not prove that the walking limit never matters; it means this small diagnostic found no reason to replace the more conservative 500 m main setting with 1,000 m. The sample is for parameter and client testing only. It is not a national accessibility estimate or a location ranking.

The journey ends at the candidate MRT exit because an exact tuition-centre unit has not been chosen. When actual units are compared later, the final walk from the MRT exit or useful bus stop to each unit should be checked separately, preferably around 300–500 m.

### Current limitation

One centre point represents every resident in a subzone. It is not each child's actual home, so the result will be an area-level accessibility estimate rather than an exact personal journey.

### What happened to failed API requests?

The first complete pass contained 31 network failures, five temporary HTTP 502 errors and 362 HTTP 200 responses without a usable PT duration. A controlled retry recovered all 36 temporary failures. The 362 repeated invalid PT responses then received successful walking results. Genuine PT-and-walking no-route pairs were evaluated under the frozen 800 m proximity rule and kept explicitly labelled.

Raw API bodies and credentials were deliberately not saved. The final cache contains only request IDs, safe categories, status codes, durations, distances and timestamps.

### Main results

The five highest weekday primary accessibility values were:

| Rank | MRT area | Accessible ages 7–16 population proxy |
|---:|---|---:|
| 1 | Sengkang | 61,450 |
| 2 | Buangkok | 55,960 |
| 3 | Punggol | 50,830 |
| 4 | Punggol Coast | 49,360 |
| 5 | Tampines | 46,360 |

Travel-time accessibility materially differed from the allocation-compatible 800 m centroid baseline under the rule frozen before national results were viewed:

- median absolute node-level difference: **560%**;
- frozen materiality threshold: **10%**;
- rank correlation: **0.614**; and
- **92 of 127** comparable MRT areas moved by at least ten ranks.

This shows why the proximity stage was only a baseline. It does not prove the top-ranked MRT areas are profitable or suitable premises.

### Quality checks

- 96,944 / 96,944 PT outcomes recorded;
- 3,969 / 3,969 required walking fallbacks recorded;
- all 146 MRT areas × two scenarios × five threshold cases exported: 1,460 rows;
- all route-coverage and output row-count gates passed;
- 212 automated tests passed; and
- the exact-credential and generic-pattern output secret scan found zero findings.

### How to explain it in a portfolio presentation

> I first used proximity as a simple national baseline, then tested whether real network travel changed the answer. I generated 96,944 public-transport journeys from 332 residential subzones to all 146 MRT areas at two frozen times. For the primary weekday case, I summed the target-age population that could arrive within 20 minutes, using a 10-minute walking fallback and a separately labelled 800 m proximity fallback only when routing was unavailable. The travel-time ranking differed materially from the straight-line baseline, so using proximity alone would have hidden important network effects.

### Where are the outputs?

- `data/processed/analysis/2026-09-17/accessibility_f7fb9e067b244fbd/`
- `reports/analysis/2026-09-17/accessibility_f7fb9e067b244fbd/analysis-summary.md`
- `reports/analysis/2026-09-17/accessibility_f7fb9e067b244fbd/h2-results.json`
- dashboard: `app/`

## Major part 3 — commercial qualification and candidate freeze (complete)

### Why was another commercial signal needed?

MP2025 zoning tells us that commercial activity is allowed or planned near an MRT area. Zoning alone does not prove that public-facing businesses actually operate there. The project therefore required a second independent positive signal before calling an area commercially qualified.

### What second signal was used?

The official [HSA retail-pharmacy dataset](https://data.gov.sg/datasets/d_bb92615f43de22933e4479558b1f6c36/view) contains geocoded licensed physical pharmacy outlets. A nearby pharmacy is evidence of current public-facing retail activity and is independent of URA zoning.

It is only a proxy. It does **not** prove that a tuition unit is available, affordable or legally suitable. No nearby pharmacy also does not prove that an area lacks other commercial activity.

### How was it tested using code?

The pass/fail rules were written before node-level results were inspected. Python then checked source freshness, coordinate quality, national and regional coverage, and counted pharmacies inside the same 400 m and 800 m union-of-exits buffers used for zoning.

```python
distance = min(exit_point.distance(pharmacy_point) for exit_point in station_exits)
pharmacy_signal = any(distance <= 800 for distance in pharmacy_distances)
qualified = zoning_signal and pharmacy_signal
```

Main files:

- `config/nodes/second_signal_preflight.json`
- `src/tuition_location_analytics/nodes/commercial_signal_preflight.py`
- `src/tuition_location_analytics/nodes/commercial_signal_apply.py`
- `reports/nodes/2026-09-18/second-commercial-signal-preflight.md`

All 11 frozen gates passed. The source contained 249 valid locations across all five regions. Ninety-six of 146 MRT areas had a pharmacy within 800 m; 95 had both the pharmacy signal and positive commercial zoning, so **95 areas qualified**.

### How were 36 areas selected?

Competitor data was deliberately not viewed. The 95 qualified areas were screened using two equally weighted measures:

1. nearby ages 7–16 population within the 800 m exit-union area; and
2. ages 7–16 population able to reach the MRT area under the primary travel-time rule.

The highest combined scores filled 24 merit slots. Twelve more slots were added deterministically to improve regional representation. The frozen result contains 8 Central, 6 East, 7 North, 8 North-East and 7 West areas.

This was the **competition-stage candidate set**, not the final recommendation. The later competition-uncertainty gate changed the final order.

Main files:

- `config/competitors/candidate_freeze.json`
- `src/tuition_location_analytics/competitors/candidate_freeze.py`
- `reports/competitors/2026-09-18/candidate_freeze_8f16c917adc6a3a3/candidate-freeze.md`

### What is the outside audit?

The project also randomly selected 40 of the remaining 59 qualified areas using a fixed seed and region × screen-band strata. These areas receive the same competitor-search method. This checks whether concentrating on the 36 candidates created an obvious blind spot and supports the later H1 analysis.

East and North have no qualified non-candidate areas left because every qualified area in those regions entered the 36. Candidate plus audit coverage still spans all five regions. Inclusion probabilities and design weights are preserved rather than pretending the audit is a full national census.

### How to explain it in a portfolio presentation

> Before looking at competitors, I required two independent signs that each MRT area had commercial context: current zoning and licensed retail presence. I froze the pharmacy-source quality rules first, qualified 95 of 146 areas, and then selected 36 using an equal balance of nearby target-age population and transit accessibility, with extra slots for regional coverage. I also froze a probability-sampled 40-area outside audit so the later competitor work can test for selection blind spots.

## Major part 4 — competitor analysis (complete)

### What was done overall?

- Ran **156/156 fixed searches** across 78 unique candidate, audit and benchmark MRT areas.
- Used search only to find leads; only current operator pages could confirm a branch.
- Verified **120 unique physical P1–S4 Mathematics branches**.
- Resolved 129 of 130 batch-specific branch locations by exact postal code; the unresolved one was excluded rather than guessed.
- Completed **3,690/3,690** national-batch routes plus 54/54 separately labelled Bukit Timah benchmark routes (**3,744 total**).
- Counted confirmed branches within the primary 10-minute walk and a 15-minute sensitivity.

This is complete execution of the fixed protocol, but not a claim that every tuition business in Singapore was found. Directory-only, online-only, home-tutor and address-incomplete results were not counted.

### Why was Bukit Timah added as a benchmark?

The frozen 36 were chosen only from nearby target-age population and transport accessibility before competitor results were viewed. That prevents circular reasoning, but those two measures do not capture every possible market factor such as family income, willingness to pay, school clusters or an area's existing reputation as a tuition hub.

Bukit Timah was therefore added as a **separately labelled benchmark**, not silently inserted into the 36. The benchmark covers Beauty World, King Albert Park, Sixth Avenue and Tan Kah Kee. Beauty World and King Albert Park were already in the frozen outside audit; the other two are benchmark-only.

### What did the benchmark show?

Two fixed web queries were run for each of the four areas. Search was used only to find leads; a centre's own website was required to confirm its address, Mathematics offering and relevant school levels. The initial batch found 12 distinct operator-page leads: 11 confirmed and one possible. This is not claimed to be a complete Bukit Timah total.

All 12 branches were geocoded by exact six-digit postal code. Python then requested the walking route from every preserved official MRT exit to each unique building and used the shortest route. All 54 route checks succeeded. The preliminary 10-minute catchment counts are:

| MRT area | Confirmed branches | Possible additional branch |
|---|---:|---:|
| Beauty World | 8 | 1 |
| King Albert Park | 2 | 0 |
| Sixth Avenue | 1 | 0 |
| Tan Kah Kee | 1 | 0 |

One branch can belong to more than one MRT catchment, so these rows must not be summed as a unique-branch total. Beauty World's 15-minute sensitivity contains nine confirmed plus one possible branch.

### What did the first national batch show during execution?

The first fixed national chunk covers eight MRT areas: Lentor, Newton, Sengkang, Chinatown, HarbourFront, Punggol, Paya Lebar and Marine Terrace. All 16 planned searches completed. Search only created leads; a centre's own site still had to confirm a current physical branch, Mathematics and a relevant P1–S4 level.

Eighteen physical in-scope branches were confirmed and all 18 exact-postal geocodes resolved. Python tested every branch building against every preserved official exit of all eight MRT areas. All 646 walking requests succeeded and produced 144 branch × MRT-area memberships.

| MRT area | Confirmed ≤10 min | Confirmed ≤15 min |
|---|---:|---:|
| Lentor | 1 | 1 |
| Newton | 1 | 1 |
| Sengkang | 1 | 1 |
| Chinatown | 1 | 1 |
| HarbourFront | 0 | 0 |
| Punggol | 1 | 1 |
| Paya Lebar | 4 | 5 |
| Marine Terrace | 0 | 3 |

This shows why the project counts by measured MRT walking catchment rather than town name. Punggol has several validated centres elsewhere in the town, but only one is within the measured Punggol MRT catchment. Marine Terrace has nearby competition under the 15-minute sensitivity, but none under the stricter 10-minute main rule.

That first batch was partial; the complete national protocol has now finished and is used in the final comparison below.

Core code:

```python
best_route = min(successful_exit_routes, key=lambda route: route.duration_seconds)
inside_primary = best_route.duration_seconds <= 10 * 60
inside_sensitivity = best_route.duration_seconds <= 15 * 60
```

Main files:

- `config/competitors/strategic_benchmarks.json`
- `config/competitors/national_query_schedule.json`
- `src/tuition_location_analytics/competitors/walking_catchment.py`
- `reports/competitors/2026-09-18/national_batch_01/national-batch-01-summary.md`
- `reports/competitors/2026-09-18/national_completion/national-competition-summary.md`

### How to explain it in a portfolio presentation

> I froze the shortlist before looking at rivals, then ran the same two search queries and operator-page validation rules across 78 candidate, audit and benchmark MRT areas. I geocoded branches by exact postal code and measured the shortest actual walking route from every official MRT exit. All 156 searches and 3,690 routes completed. The Bukit Timah benchmark confirmed that famous tuition hubs can be dense with competitors, while the final model deliberately looks for a better balance of demand, access and competitive space.

## Major part 5 — H1 and financial sensitivity (complete)

### What did H1 show?

The predeclared expectation was that areas reachable by more target-age residents would tend to contain more confirmed tuition branches. Combining all 36 candidates with the probability-weighted 40-area outside audit produced a positive descriptive correlation of **0.318**. The expected direction was observed, but the result remains **inferentially inconclusive** because no confidence interval, spatial-dependence correction or causal design was applied. It does not prove that competition causes success or that highly competitive hubs are best for a new entrant.

### How was finance handled without inventing local rents?

The same three illustrative operator assumptions were applied to every MRT area. They are not market-rent observations or forecasts.

| Case | Occupancy assumption/month | Break-even students | Illustrative capacity used |
|---|---:|---:|---:|
| Cautious | SGD 12,000 | 123 | 68% |
| Base | SGD 9,000 | 83 | 46% |
| Upside | SGD 6,000 | 54 | 30% |

Because no licensed node-specific rent source was available, finance was kept equal between areas. This is more honest than making up local rent differences to force a ranking.

Main files:

- `config/modelling/operator_scenarios.json`
- `src/tuition_location_analytics/analysis/final_decision.py`
- `reports/analysis/2026-09-18/final_decision/final-decision.json`

## Major part 6 — final conditional recommendations (complete)

### How were the final recommendations chosen?

The 36 frozen candidates were compared on four dimensions:

1. nearby ages 7–16 population proxy;
2. travel-time accessibility;
3. confirmed direct competitors, where fewer is better; and
4. common financial feasibility assumptions.

The analysis used 10 frozen accessibility cases, 10- and 15-minute confirmed competitor counts, a conservative zero-confirmed stress test and five preference profiles. This produced **40 location-sensitivity scenarios and 200 profile evaluations**, with 106 unique full rank orderings. The three financial cases were evaluated separately because identical assumptions for every location cannot change the location ranking.

The national batches did not retain every possible or unresolved lead consistently enough to publish an honest `confirmed + possible` upper bound. Instead of inventing one, the stress test scores zero confirmed discoveries as one competition unit solely to remove the automatic best-score advantage. A release recommendation must receive at least one top-three selection under both the observed and caution cases.

| Conditional rank | MRT area | Overall top-three frequency | Caution-case frequency | Confirmed found ≤10 min |
|---|---|---:|---:|---:|
| 1 | Sengkang | 100% | 100% | 1 |
| 2 | Serangoon | 19% | 20% | 1 |

Sengkang is the clearly robust result. Serangoon is a weaker but defensible second alternative because it appears under both competition treatments. Yishun and Bukit Panjang remain on a **competition-recheck watchlist**: both ranked well under observed confirmed counts, but neither received a top-three selection when the automatic advantage from zero confirmed discoveries was removed.

These are **conditional MRT-area alternatives**, not proof that a suitable unit is available and not advice to open both centres. Before a lease decision, verify the actual unit, all-in rent, permitted use, owner consent, fire safety, room/timetable capacity, registration requirements and local parent demand.

### One-line portfolio presentation

> I screened all 146 MRT areas, narrowed them to 36 without using competitor data, audited rivals with 156 fixed searches and 3,744 walking routes, and tested 40 location scenarios under five preference profiles. A final uncertainty gate prevented zero confirmed discoveries from automatically looking best. Sengkang and Serangoon survived; Yishun and Bukit Panjang moved to a recheck watchlist. The output is an evidence-led due-diligence shortlist, not a guaranteed lease recommendation.

Final dashboard data: `app/public/data/final-analysis.json`.
