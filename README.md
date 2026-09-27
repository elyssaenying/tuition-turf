# Singapore Tuition Location Intelligence

For a short, presentation-friendly explanation of the analysis, data, code, reasoning, and limitations, see [`must_know.md`](must_know.md).

**Where Should a P1–S4 Mathematics Tuition Operator Open a New Centre?**

A reproducible undergraduate data-analysis portfolio project for an operator opening its first physical centre or expanding an existing network in Singapore. The completed output is an evidence-led shortlist of commercial nodes, supported by demand and competition analysis, explicit operating scenarios, break-even modelling, Pareto comparison and uncertainty analysis. Current-unit eligibility remains a later due-diligence layer.

**Status: the core portfolio analysis and dashboard are complete, with accepted limitations stated.** The project screened all 146 current MRT areas, completed 96,944 public-transport route requests from 332 residential-subzone centre points and froze 36 candidates before inspecting competitor evidence. The decision-relevant competitor design then compared those candidates with a probability-sampled 40-area outside audit. H1 is a positive but inferentially inconclusive design-weighted descriptive association (`r = 0.318`); H2 shows that route-based accessibility materially changes the simpler centroid-distance picture. The final comparison evaluates 40 demand/accessibility/competition cases under five frozen preference profiles (200 profile evaluations, 106 unique full rank orderings) and reports the three common finance cases separately because identical assumptions across locations cannot change their order. **Sengkang and Serangoon** meet the release rule under both observed-confirmed and zero-confirmed-caution competition cases, although Sengkang is materially more robust. These are MRT-area alternatives for premises due diligence—not guaranteed business outcomes or current-unit recommendations. Full history is preserved in the decision log.

The bounded competitor-intelligence pilot (D41–D52) froze branch-level scope/evidence rules, reconciled 40 query records to a private 121-observation ledger, limited credit to candidate-specific validation, and retained the D44 deterministic physical-branch identity rule. The approved run records 27 confirmed, 28 possible and 9 unresolved retained branches; 51 resolved, 1 ambiguous and 12 missing-postal geocodes; and 94/94 exact observations represented exactly once across retained/excluded outputs. Five aggregate brand diagnostics retain zero validation credit. S010-derived evidence remains private and historical public reports are not authorised for publication. D52 approves the method only; later decisions freeze the national candidate and outside-audit design. See the [decision sheet](docs/national-design-decision-sheet.md) and [national competitor design](docs/national-competitor-design.md).

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
│   ├── analysis/                  # Proximity, routing, H1/H2 and final decision
│   ├── competitors/               # Frozen discovery, audit and walking catchments
│   └── nodes/                     # Station complexes and commercial qualification
├── data/
│   ├── raw/                       # Immutable acquired snapshots, ignored by default
│   ├── interim/                   # Rebuildable working tables, ignored by default
│   └── processed/                 # Validated analytical exports, ignored by default
├── app/
│   ├── src/                       # React/TypeScript dashboard
│   └── public/data/               # Approved static export bundle
├── config/
│   ├── preflight/                 # Fixed, non-recommendation coverage fixtures
│   └── foundation/                # Frozen source and processing configuration
├── tests/                         # Preflight and foundational transformation tests
├── docs/                          # Project and data contracts
└── reports/
    ├── preflight/                 # Redacted machine/readable preflight evidence
    ├── foundation/                # Manifest, quality, join and completion reports
    └── analysis/                  # Audited analytical and release reports
```

Raw, interim and processed data remain ignored. The reusable code, configuration, tests and redacted reports occupy their documented paths.

## Architecture and workflow

Python 3.12 performs acquisition, cleaning, geospatial analysis, modelling and versioned data export. The foundational runtime pins PyArrow, pyproj and Shapely for Parquet, EPSG:3414 transformation and geometry validation; `requirements.lock` records the complete installed dependency set. The React/TypeScript dashboard consumes only precomputed, redacted static tables. No backend is required for the portfolio release.

Completed core flow: registered source → immutable raw snapshot → validated interim tables → harmonised geographic and branch tables → common financial scenarios → Pareto and five-profile sensitivity comparison → competition-uncertainty gate → conditional commercial-node shortlist → validated exports, release manifest and static dashboard bundle. Optional later layers include current-unit due diligence, licensed node-specific rent integration, parent validation, Monte Carlo and expansion cannibalisation. The interface explains calculations and limitations and does not recompute substantive models independently.

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

This reuses the immutable S026/S027 snapshots, applies `config/nodes/station_overrides.json`, `config/nodes/review_dispositions.json`, `config/nodes/operational_status_evidence.json` and `config/nodes/system_map_roster.json` (a versioned derived registry backed by the immutable `data/raw/s032_lta_system_map/` snapshot), and writes outputs under `data/processed/nodes/2026-09-13/` and evidence under `reports/nodes/2026-09-13/`, including a previous-to-current station-complex mapping and a full review queue with dispositions. This immutable upstream run intentionally records zero formally qualified nodes because it contains only the first commercial-signal family. D64 later executed the independently frozen S034 licensed-retail signal without rewriting this run: 95 of 146 MRT areas satisfied both the MP2025 zoning and licensed-retail rules and became the eligible universe for the frozen candidate and outside-audit selection. Reproducing this command alone does not reproduce the later qualification, competition or final recommendation stages.

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

The current immutable run is `proximity_baseline_965a36240409d092`. It evaluates all 146 MRT-area candidates, unions 800 m and 1,200 m EPSG:3414 buffers around every preserved station exit, and allocates each subzone's ages 7–16 population proxy by intersected polygon area. Outputs are under `data/processed/analysis/2026-09-17/<run_id>/` and `reports/analysis/2026-09-17/<run_id>/`. An identical rerun aborts rather than overwriting its directory. This baseline is not used alone: the completed final comparison combines it with audited travel-time accessibility and competition evidence.

## Accessibility preparation and bounded comparison

The corrected offline national plan is `routing_plan_d17bea62d5e154ae`: 332 subzone-centroid origins × 146 MRT areas × two frozen times = 96,944 unique PT requests using the approved 500 m main walking setting. Request IDs include the walking setting and other request-defining parameters, preventing cross-setting cache collisions.

Bounded run `walk_comparison_11ab30dda2b46b67` safely tested the same 20 deterministic pairs at 300 m, 500 m and 1,000 m. All three settings produced identical pair-level PT status and duration in this diagnostic. The separately approved national execution is complete with a resumable redacted cache. Final safe progress is recorded in `reports/analysis/2026-09-17/national_routing_execution_routing_plan_d17bea62d5e154ae/progress.json`; audited accessibility outputs are in `reports/analysis/2026-09-17/accessibility_f7fb9e067b244fbd/`.

## Reproduce the final comparison

The tracked redacted candidate/audit inputs, accessibility table and aggregate competition snapshot are sufficient to reproduce the final public comparison. When the private local ledgers exist, the same command rebuilds the safe aggregates from them first. Run:

```sh
PYTHONPATH=src .venv/bin/python -m tuition_location_analytics.analysis.final_decision --repo-root .
cd app && npm run build
```

The first command validates the completed internal competitor collection, restricts H1 and recommendation calculations to the 36 frozen candidates and 40 probability-sampled outside-audit areas, applies 10/15-minute confirmed-count and zero-confirmed-caution competition cases, evaluates 40 location cases under five profiles, and exports the public dashboard bundle. Finance is reported across three illustrative cases but not multiplied into the location-ranking denominator. Final evidence, release QA and checksums are in `reports/competitors/2026-09-18/national_completion/`, `reports/analysis/2026-09-18/final_decision/` and `app/public/data/final-analysis.json`.
