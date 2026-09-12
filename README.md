# Singapore Tuition Location Intelligence

**Where Should a P1–S4 Mathematics Tuition Operator Open a New Centre?**

A reproducible undergraduate data-analysis portfolio project for an operator opening its first physical centre or expanding an existing network in Singapore. The eventual output is an evidence-led shortlist of commercial nodes, supported by demand and competition analysis, explicit rental and operating scenarios, break-even modelling, Pareto comparison, and uncertainty analysis. Current-unit eligibility is a later due-diligence layer.

**Status: foundational nationwide acquisition completed with documented warnings.** Run `foundation_7dbd9a143e9504e7` fully ingested S001 and acquired immutable S003–S006 snapshots. It produced validated population, MP2019 boundary/crosswalk, school, MRT-exit and bus-stop tables. All 332 S001 subzones matched S003 exactly after case/whitespace normalization; no fuzzy match was used. S007 remains `verified_limited`: its fixed preflight returned 30/30 walking routes and 19/30 PT routes, with 11 explicit HTTP 404/missing routes and no rate limiting. Missing PT routes require the documented walking/proximity fallback and are never imputed. No competitor inventory, national routing matrix, node score, model, dashboard or location recommendation has been produced. Current premises evidence remains a blocker only for unit-level or lease-ready recommendations.

## Decision contract

Screen Singapore broadly and compare commercial nodes using demand, accessibility, competition and transparent financial scenarios. Conditional node recommendations use a generic `operator_assumption` monthly occupancy-cost grid, state every rent value and show sensitivity; URA street-level rental statistics (S016) remain restricted manual context and are not a publishable analytical input or a basis for node-specific ranges. Specific-premises investigation is optional later due diligence. Only current unit-specific premises evidence satisfying every mandatory URA/SCDF/use and owner-consent requirement can support `verified_eligible`, and that status covers premises requirements only—not school/operator registration or ordinary commercial and lease due diligence. Count competitor branches separately from brands; treat resident ages 7–16 as a population proxy rather than observed demand or customers, and keep direct mathematics competition separate from exploratory education-cluster effects. Report trade-offs and uncertainty rather than presenting Pareto membership or a weighted ranking as objective truth.

The scope validated by this project will be P1–S4 mathematics only. Shared components may later be reused for other subjects, but those subjects have not been analysed or validated.

## Structure

```text
.
├── README.md
├── .gitignore
├── .env.example
├── src/tuition_location_analytics/
│   ├── preflight/                 # Bounded S001/S007 acquisition and validation
│   ├── foundation/                # Nationwide public-source acquisition and processing
│   ├── pipelines/                 # Future analytical pipeline stages
│   ├── geospatial/                # Future boundaries, joins and catchments
│   └── modelling/                 # Future demand, finance and Pareto calculations
├── data/
│   ├── raw/                       # Immutable acquired snapshots, ignored by default
│   ├── interim/                   # Rebuildable working tables, ignored by default
│   └── processed/                 # Validated analytical exports, ignored by default
├── app/
│   ├── src/                       # Future React/TypeScript interface
│   └── public/data/               # Future approved static export bundle
├── config/
│   ├── preflight/                 # Fixed, non-recommendation coverage fixtures
│   └── foundation/                # Frozen source and processing configuration
├── tests/                         # Preflight and foundational transformation tests
├── docs/                          # Project and data contracts
└── reports/
    ├── preflight/                 # Redacted machine/readable preflight evidence
    ├── foundation/                # Manifest, quality, join and completion reports
    └── figures/                   # Future analysis narrative and figures
```

Raw, interim and processed data remain ignored. The reusable code, configuration, tests and redacted reports occupy their documented paths.

## Architecture and workflow

Python 3.12 performs acquisition, cleaning, geospatial analysis, modelling and versioned data export. The foundational runtime pins PyArrow, pyproj and Shapely for Parquet, EPSG:3414 transformation and geometry validation; `requirements.lock` records the complete installed dependency set. A React/TypeScript application will later consume small, precomputed static tables. A backend is deferred until a documented requirement justifies one.

Planned core flow: registered source → immutable raw snapshot → validated interim tables → harmonised geographic and branch tables → node-level financial scenarios → Pareto and five-profile sensitivity comparison → conditional commercial-node shortlist → validated processed exports → analytical report and static dashboard bundle. Optional later layers include current-unit due diligence, licensed node-specific rent integration, Monte Carlo, expansion cannibalisation, cluster effects and exhaustive national manual branch validation. Each stage must preserve source lineage, dates and quality flags. The interface will explain calculations and limitations and will not recompute substantive models independently.

`.env.example` lists variable names only. The preflight reads OneMap credentials from the ignored local `.env`, generates a token in memory and never persists credentials, tokens, request headers or raw authentication responses. Every foundation run performs generic secret-pattern scanning over reportable text outputs. When credential values are loaded, the scan also compares outputs with those exact values. Any match fails the run; when credentials are unavailable, a clean cached run continues with a warning and records limited assurance because exact-value comparison was not performed. Only safe finding paths, counts and comparison status may be retained. Do not place credentials in source files or browser assets. Large inputs and generated data are excluded by default; later publication needs an explicit size, licence and privacy review.

## Read the contract

- [Project charter](docs/project-charter.md): question, scope, units and limitations.
- [Decision framework](docs/decision-framework.md): eligibility, hypotheses, trade-offs and recommendation rules.
- [Methodology plan](docs/methodology-plan.md): geographic design, branch validation, finance and uncertainty.
- [Data contracts](docs/data-contracts.md): table grains, field meanings and output interface.
- [Source register](docs/source-register.md): verified source pages, access/licence findings and blockers.
- [Source-feasibility matrix](docs/source-feasibility-matrix.md): requirement-level fields, grain, coverage, fallbacks and acquisition verdicts.
- [Data-quality plan](docs/data-quality-plan.md): checks and publication gates.
- [Definition of done](docs/definition-of-done.md): current-pass and eventual completion criteria.
- [Decision log](docs/decision-log.md): provisional choices and required reviews.

## Reproduce the foundational phase

Create a Python 3.12 environment, install the locked dependencies, and run:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
PYTHONPATH=src .venv/bin/python -m tuition_location_analytics.foundation.cli --repo-root .
```

The command checksum-verifies and reuses existing immutable snapshots. Its redacted school-geocode cache makes an identical rerun perform zero further OneMap searches. `config/foundation/run.json` explicitly selects both the foundation snapshot date and the existing preflight-result artifact; the latter must exist. The configured date controls immutable raw lookup plus foundation processed, report and geocode-cache directories, so a future snapshot cannot silently reuse an earlier output directory. For the current configured snapshot, outputs remain under `data/processed/foundation/2026-09-12/` and evidence under `reports/foundation/2026-09-12/`. S001 raw redistribution permission remains unresolved, so keep the ignored ZIP out of public outputs. Stop before competitor acquisition, national routing, node scoring, modelling or dashboard work.
