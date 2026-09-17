# Singapore Tuition Location Intelligence

For a short, presentation-friendly explanation of the analysis, data, code, reasoning, and limitations, see [`must_know.md`](must_know.md).

**Where Should a P1–S4 Mathematics Tuition Operator Open a New Centre?**

A reproducible undergraduate data-analysis portfolio project for an operator opening its first physical centre or expanding an existing network in Singapore. The eventual output is an evidence-led shortlist of commercial nodes, supported by demand and competition analysis, explicit rental and operating scenarios, break-even modelling, Pareto comparison, and uncertainty analysis. Current-unit eligibility is a later due-diligence layer.

**Status: the nationwide proximity baseline is complete and the approved national accessibility-routing run is in progress.** Run `proximity_baseline_965a36240409d092` compares all 146 current MRT-area candidates using an area-weighted ages 7–16 population proxy inside 800 m exit-union proximity catchments, with a 1,200 m sensitivity. The corrected 500 m routing plan `routing_plan_d17bea62d5e154ae` covers 332 subzone origins × 146 nodes × 2 frozen times = 96,944 planned PT requests and includes the walking parameter in every cache-safe request ID. Approved bounded run `walk_comparison_11ab30dda2b46b67` found identical pair-level statuses/durations at 300/500/1,000 m and supports retaining 500 m. D59 authorises the full plan; D60 adds controlled concurrency while keeping the four-request-starts-per-second ceiling, plus completion-gated accessibility/H2 aggregation. No accessibility result exists until the cache and required fallbacks are complete and audited. Quality checks and the 209-test project suite pass. The proximity result is not observed demand, a shortlist or a recommendation. The private competitor-method pilot remains approved for design planning only, and zero nodes are formally `qualified` until the second independent commercial signal is completed. Full history is in the decision log (D01–D60).

The bounded competitor-intelligence pilot (D41–D52) froze branch-level scope/evidence rules, reconciled 40 query records to a private 121-observation ledger, limited credit to candidate-specific validation, and retained the D44 deterministic physical-branch identity rule. The approved run records 27 confirmed, 28 possible and 9 unresolved retained branches; 51 resolved, 1 ambiguous and 12 missing-postal geocodes; and 94/94 exact observations represented exactly once across retained/excluded outputs. Five aggregate brand diagnostics retain zero validation credit. S010-derived evidence remains private and historical public reports are not authorised for publication. D52 approves only national-design planning, not national collection or location ranking. The proposed next design first resolves the second-commercial-signal requirement, then runs separately authorised national demand/accessibility, freezes a non-competitor candidate set, and validates competition in candidate catchments plus a reproducible outside audit. The owner choices remain unapproved; see the [decision sheet](docs/national-design-decision-sheet.md) and [national competitor design](docs/national-competitor-design.md).

**Historical-run note:** D46, D49 and D51's incomplete private output remain preserved non-authoritative audit history. D52's independently audited run is the authoritative method-pilot result; it does not turn the pilot into national coverage.

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

## Reproduce the station-complex and commercial-node phase

With the same environment active, run:

```sh
PYTHONPATH=src .venv/bin/python -m tuition_location_analytics.nodes.cli --repo-root .
```

This reuses the immutable S026/S027 snapshots, applies `config/nodes/station_overrides.json`, `config/nodes/review_dispositions.json`, `config/nodes/operational_status_evidence.json` and `config/nodes/system_map_roster.json` (a versioned derived registry backed by the immutable `data/raw/s032_lta_system_map/` snapshot), and writes outputs under `data/processed/nodes/2026-09-13/` and evidence under `reports/nodes/2026-09-13/`, including a previous-to-current station-complex mapping and a full review queue with dispositions. No node is `qualified` yet: MP2025 zoning is the only implemented commercial-signal family, and the documented second-independent-signal validation protocol (see the commercial-evidence methodology report) has not been executed. Stop before competitor acquisition, national routing, financial modelling or dashboard work.

## Reproduce the competitor-intelligence pilot

Before a future private rerun, the only permitted credential readiness check is:

```sh
PYTHONPATH=src .venv/bin/python -m tuition_location_analytics.competitors.auth_preflight --repo-root .
```

It performs at most one authentication request and no search or routing request, writes no output file, and prints only safe status/count JSON. Do not substitute the older combined `preflight.cli` command: it is a broader S001/S007 preflight and is not authentication-only.

With the same environment active, run:

```sh
PYTHONPATH=src .venv/bin/python -m tuition_location_analytics.competitors.cli --repo-root .
```

This reads tracked protocol/configuration inputs in `config/competitors/` (including `pilot_run.json`, which supplies the analysis cutoff and both private-ledger references) plus the private ignored S010-containing observation and candidate-validation ledgers named by that config. It validates the exact 40-query protocol and reconciles every query total to its linked observations before producing anything; applies candidate-specific canonical fields before exact deduplication, and may resolve a missing unit only when a single complete linked canonical identity supports the same deterministic building key. It counts validation coverage once per resulting physical branch while retaining every linked validation attempt as provenance, calculates retained S010/web overlap from canonical branch IDs, and assigns planning area only from a geocoded coordinate. A resolved retained coordinate must be inside the frozen selected planning-area set; an outside result is preserved as an excluded branch, and an inside-set searched/derived mismatch is explicitly reviewed. Brands, retained evidence and offerings are rebuilt only from retained branches. Outputs retaining S010-derived evidence are private local files under ignored `data/processed/competitors/pilot-<cutoff>/<run_id>/` and `data/interim/competitors/reports/pilot-<cutoff>/<run_id>/`, not `reports/competitors/`; an existing run-ID directory aborts before any overwrite. A fresh clone cannot reproduce this pilot without separately authorised private evidence access. Unit tests, compilation and dependency checks are separate release-verification work and are never represented as having run inside the production pipeline. The D52 run is approved as a 10-of-55-area method pilot only: it is not usable to rank locations or claim national coverage. Stop before national acquisition, routing, scoring, financial modelling, recommendation or dashboard work unless the relevant phase and its parameters are separately approved.

## Reproduce the national proximity-demand baseline

This offline stage uses only approved processed foundation/node inputs:

```sh
PYTHONPATH=src .venv/bin/python -m tuition_location_analytics.analysis.proximity_cli --repo-root .
```

The current immutable run is `proximity_baseline_965a36240409d092`. It evaluates all 146 MRT-area candidates, unions 800 m and 1,200 m EPSG:3414 buffers around every preserved station exit, and allocates each subzone's ages 7–16 population proxy by intersected polygon area. Outputs are under `data/processed/analysis/2026-09-17/<run_id>/` and `reports/analysis/2026-09-17/<run_id>/`. An identical rerun aborts rather than overwriting its directory. Do not use this baseline alone to shortlist or recommend a location; the frozen national transit/walking calculation and H2 comparison remain outstanding.

## Accessibility preparation and bounded comparison

The corrected offline national plan is `routing_plan_d17bea62d5e154ae`: 332 subzone-centroid origins × 146 MRT areas × two frozen times = 96,944 unique PT requests using the approved 500 m main walking setting. Request IDs include the walking setting and other request-defining parameters, preventing cross-setting cache collisions.

Bounded run `walk_comparison_11ab30dda2b46b67` safely tested the same 20 deterministic pairs at 300 m, 500 m and 1,000 m. All three settings produced identical pair-level PT status and duration in this diagnostic. The separately approved national execution is now in progress with a resumable redacted cache. Current safe progress is written to `reports/analysis/2026-09-17/national_routing_execution_routing_plan_d17bea62d5e154ae/progress.json`; do not treat partial progress as a national accessibility result or location ranking.
