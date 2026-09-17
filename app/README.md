# Dashboard first cut

This is a local design preview for the portfolio dashboard. It uses the completed
146-node proximity baseline and station-anchor coordinates. Accessibility,
competition, finance and recommendation sections are deliberately labelled as
in progress or planned; the interface does not invent unfinished results.

## Run locally

```sh
cd app
npm install
npm run dev
```

Open the local URL printed by Vite. Create a production build with
`npm run build`.

## Local preview data

The ignored preview files in `app/public/data/` are copied from:

- `data/processed/analysis/2026-09-17/proximity_baseline_965a36240409d092/node_proximity_metrics.csv`
- `data/processed/nodes/2026-09-13/node_inspection.geojson`
- `data/processed/foundation/2026-09-12/mp2019_subzones.geojson`

The final release should consume an explicitly approved, versioned static export
bundle after the remaining analysis and publication checks are complete.
