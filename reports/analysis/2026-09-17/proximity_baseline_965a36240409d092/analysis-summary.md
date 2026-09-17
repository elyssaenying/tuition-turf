# National MRT-area proximity-demand baseline

Run ID: `proximity_baseline_965a36240409d092`  
Status: `passed_with_warnings`  
Nodes analysed: **146**

## What this result means

This is the first nationwide comparison of the 146 approved MRT-area candidates. It estimates the ages 7–16 resident population spatially overlapping the union of straight-line buffers around every preserved station exit. Population is allocated by intersected subzone area.

It is a **proximity proxy**, not public-transport travel time, observed enrolment, customers or a final location recommendation. Overlapping node catchments are evaluated independently and must not be summed.

## Highest 800 m proxy values

| Rank | MRT area | Population proxy | 1,200 m sensitivity | Bus stops within 800 m | Schools within 800 m |
|---:|---|---:|---:|---:|---:|
| 1 | SENGKANG MRT STATION | 10084 | 21505 | 58 | 9 |
| 2 | PUNGGOL MRT STATION | 9214 | 18470 | 50 | 6 |
| 3 | ADMIRALTY MRT STATION | 8954 | 14160 | 52 | 8 |
| 4 | BUANGKOK MRT STATION | 7012 | 15635 | 54 | 6 |
| 5 | TAMPINES MRT STATION | 6681 | 12982 | 53 | 8 |
| 6 | WOODLANDS MRT STATION | 6200 | 12237 | 65 | 6 |
| 7 | TAMPINES EAST MRT STATION | 6128 | 11694 | 50 | 10 |
| 8 | BUKIT PANJANG MRT STATION | 5982 | 12040 | 58 | 6 |
| 9 | BOON LAY MRT STATION | 5770 | 10139 | 47 | 4 |
| 10 | PIONEER MRT STATION | 5738 | 10207 | 48 | 4 |

## Quality and limitations

- All 146 current node candidates were processed and have station exits.
- Input target-age population proxy: 412,630.
- Monotonic sensitivity check (1,200 m ≥ 800 m): passed.
- Uniform population within each subzone is an approximation; residential land is not evenly distributed.
- Seven schools with unresolved coordinates are omitted from spatial school counts.
- Bus-stop and school counts are context only and are not a measured accessibility score.
- National OneMap routing, H2, competition, finance and final recommendations remain outstanding.

## Next analytical step

Implement the frozen transit/walking accessibility calculation and compare it with this straight-line baseline. Do not narrow to final candidates from this proxy alone.
