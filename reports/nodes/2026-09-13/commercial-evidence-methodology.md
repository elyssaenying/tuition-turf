# Commercial-evidence methodology

Run ID: `nodes_0a34bc5be80d0c27`

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

## Second independent-signal validation protocol (documented, not yet implemented)

Status: `documented_not_implemented`. A nationwide HDB commercial-building join or comparable geocoding exercise was explicitly out of scope for this bounded correction; MP2025 zoning remains the only implemented signal family, so no node in this run may be marked qualified.

1. Freeze a predeclared expanded shortlist of candidate nodes (provisional plus needs_manual_review nodes worth testing) before looking at any second-signal result, so the source of the shortlist cannot be chosen to fit a preferred outcome.
2. Use one current, legally reusable and independently verifiable commercial-presence source that is not itself a source of tuition-competitor evidence and not MP2025 zoning (for example a licensed/open business-registration-with-address feed, a permitted commercial-directory export, or an authorised OneMap thematic commercial layer, subject to its own source-feasibility and licence check before use).
3. Validate every node on the predeclared shortlist against that source using the same buffer methodology and thresholds as the zoning signal; do not selectively validate only the nodes that already look preferred.
4. Record measurement_status/positive_signal/missing_reason for every shortlist node exactly as the zoning evidence rows do, so missing evidence stays null rather than being treated as a negative or a zero.
5. If any shortlisted candidate fails the second-signal check, remove it and recompute the shortlist from the remaining predeclared pool; repeat validation on the recomputed shortlist rather than patching the result.
6. Repeat steps 3-5 until the eligible shortlist is stable (no further removals).
7. A node may only move from provisional to qualified once it has at least two independent positive signal families evaluated this way; zoning bands (400 m/800 m) still count as one family, never two.
8. None of this establishes occupancy, current availability, quoted rent or premises permission; it only raises confidence that a commercial-use signal is genuinely independent of zoning classification.

No node may be marked `qualified` until this protocol is executed and passes; `provisional` nodes remain in the analytical candidate pool in the meantime.

## Interpretation limits

MP2025 is Dec 2025 zoning context, while population remains on MP2019 subzones. Zoning does not prove current occupancy, availability, quoted rent, owner consent, permitted tuition use or URA/SCDF eligibility.
