# Commercial-evidence methodology

Run ID: `nodes_afd024de462faab3`

## Frozen evidence definition

MP2025 accepted categories:

- `COMMERCIAL`
- `COMMERCIAL & RESIDENTIAL`
- `COMMERCIAL / INSTITUTION`
- `RESIDENTIAL WITH COMMERCIAL AT 1ST STOREY`

Business/industrial, White, hotel, educational and unrelated land uses are excluded. The accepted categories are explicit commercial or explicit commercial-mixed zoning labels.

Evidence is calculated inside unioned 400 m and 800 m straight-line buffers around every valid exit in a complex, using EPSG:3414. These bands are proximity measurements, not walking times. Intersections report relevant area, buffer share, feature count, category areas and nearest distance.

## Independence and qualification

A `qualified` node requires at least `2` independent positive signal families at 800 m. The two MP2025 bands are measurements of one zoning signal, not two independent signals. A station is an accessibility anchor and is never counted as commercial evidence.

The HDB property table's commercial flag could not be deterministically linked to HDB building geometry: the tables expose no shared stable identifier, and the building layer's street code is opaque. No uncertain address join or large OneMap geocode was performed. The missing HDB signal remains null rather than zero.

## Interpretation limits

MP2025 is Dec 2025 zoning context, while population remains on MP2019 subzones. Zoning does not prove current occupancy, availability, quoted rent, owner consent, permitted tuition use or URA/SCDF eligibility.
