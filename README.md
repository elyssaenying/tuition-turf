# Singapore Tuition Location Intelligence

**Where Should a P1–S4 Mathematics Tuition Operator Open a New Centre?**

A reproducible undergraduate data-analysis portfolio project for an operator opening its first physical centre or expanding an existing network in Singapore. The eventual output is an evidence-led shortlist of commercial nodes, supported by premises eligibility, demand and competition analysis, break-even modelling, Pareto comparison, and uncertainty analysis.

**Status: specification and repository scaffold only.** No data has been acquired, sources verified, analysis implemented, packages installed, dashboard built, or location findings produced. No location is currently recommended.

## Decision contract

Screen Singapore broadly, compare commercial nodes, and assess specific premises before making recommendations. Count competitor branches separately from brands. Use resident children approximately aged 7–16 as a demand proxy; this is not a count of prospective customers. Treat direct mathematics competition separately from exploratory education-cluster effects. Public evidence can support a `screened_feasible` premises and therefore a conditional node shortlist, but the remaining permission or landlord confirmation must stay visible. Only unit-specific authoritative evidence satisfying every mandatory requirement can support `verified_eligible` status and a fully recommended or lease-ready premises. Report trade-offs and uncertainty rather than presenting a weighted score as objective truth.

The scope validated by this project will be P1–S4 mathematics only. Shared components may later be reused for other subjects, but those subjects have not been analysed or validated.

## Structure

```text
.
├── README.md
├── .gitignore
├── .env.example
├── src/tuition_location_analytics/
│   ├── pipelines/                 # Future acquisition, cleaning and export stages
│   ├── geospatial/                # Future boundaries, joins and catchments
│   └── modelling/                 # Future demand, finance and Pareto calculations
├── data/
│   ├── raw/                       # Immutable acquired snapshots, ignored by default
│   ├── interim/                   # Rebuildable working tables, ignored by default
│   └── processed/                 # Validated analytical exports, ignored by default
├── app/
│   ├── src/                       # Future React/TypeScript interface
│   └── public/data/               # Future approved static export bundle
├── tests/                         # Future transformation and model validation
├── docs/                          # Project and data contracts
└── reports/
    └── figures/                   # Future analysis narrative and figures
```

Empty working directories contain `.gitkeep`. They do not contain sample observations or executable scaffolding. Report text can later live directly in `reports/`.

## Architecture and workflow

Python 3.12 will perform acquisition, cleaning, geospatial analysis, modelling and versioned data export. A React/TypeScript application will consume small, precomputed static tables. A backend is deferred until a documented requirement justifies one. Package manifests, lockfiles and runtime setup belong to implementation, after source feasibility is checked.

Planned flow: registered source → immutable raw snapshot → validated interim tables → harmonised geographic and branch tables → premises screening and verification → scenario analysis → Pareto/sensitivity comparison → validated processed exports → static dashboard bundle. Each stage must preserve source lineage, dates and quality flags. The interface will explain calculations and limitations and will not recompute substantive models independently.

`.env.example` is a non-secret template for future local configuration; it is not loaded by any code at this stage. Do not place credentials in source files or browser assets. Large inputs and generated data are excluded by default; later publication needs an explicit size, licence and privacy review.

## Read the contract

- [Project charter](docs/project-charter.md): question, scope, units and limitations.
- [Decision framework](docs/decision-framework.md): eligibility, hypotheses, trade-offs and recommendation rules.
- [Methodology plan](docs/methodology-plan.md): geographic design, branch validation, finance and uncertainty.
- [Data contracts](docs/data-contracts.md): table grains, field meanings and output interface.
- [Source register](docs/source-register.md): evidence requirements and unverified discovery leads.
- [Data-quality plan](docs/data-quality-plan.md): checks and publication gates.
- [Definition of done](docs/definition-of-done.md): current-pass and eventual completion criteria.
- [Decision log](docs/decision-log.md): provisional choices and required reviews.

## Next implementation task

Perform a source-feasibility and contract-validation pass: directly open authoritative source pages for resident age-by-area data, geographic boundaries, schools, transport, competitor branches, premises-use eligibility and rental evidence; record exact URLs, coverage, vintage, access/licence constraints and verified field/grain samples in the source register; then revise data contracts and resolve the geographic/age feasibility decisions. Do not begin bulk acquisition until this review establishes a viable minimum dataset. No source URLs are supplied or claimed verified in this scaffold.
