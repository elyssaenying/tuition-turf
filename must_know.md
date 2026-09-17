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

The project has not selected the final three areas yet.

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

## Major part 2 — real travel accessibility (in progress)

### What will it answer?

Can the target-age population realistically reach each MRT area by public transport and walking at the selected journey times?

The purpose is **not** to check whether an MRT area has public transport—it obviously does. The purpose is to estimate how many school-age residents can reach that MRT area conveniently.

Each planned journey starts at the centre point of one residential subzone and ends at the closest preserved exit of the candidate MRT area. The public-transport route may use buses, MRT, or both. Starting at the resident's nearest MRT would incorrectly ignore the first part of the journey from home to that station.

The main accessibility rule is a journey of **20 minutes or less**. The analysis will also check 15 minutes as a stricter case and 25 minutes as a more generous case. A 40-minute journey with multiple transfers therefore does not count as the main target audience.

The code and offline national request plan exist. The approved resumable national run started on 2026-09-17 and covers 332 subzone starting points, 146 MRT areas, and two journey-time scenarios, or 96,944 planned public-transport requests before fallbacks. It runs at a conservative 240 requests per minute in 5,000-request saved chunks. Until every route and required fallback is complete and audited, it remains an in-progress data-acquisition stage rather than a national accessibility result.

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

## Later major parts

The following sections will be completed as their analyses are completed:

- national competitor analysis;
- financial and break-even analysis;
- comparison and robustness analysis;
- final conditional recommendations and dashboard.

For each part, this guide will record the question, code, data sources, derivation, reasoning, results, limitations, quality checks, and a short presentation script.
