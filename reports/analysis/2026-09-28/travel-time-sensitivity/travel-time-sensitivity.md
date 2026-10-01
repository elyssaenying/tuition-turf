# Travel-time sensitivity: 15, 20 and 25 minutes

The question is whether changing the assumed travel limit changes which MRT areas are investigated and how the already investigated areas compare. This audit preserves the published results and applies the original selection and ranking rules to existing data.

**Main result:** Sengkang remains a top-three area under all three tested travel limits. Serangoon is selected in 37 of 40 setting comparisons at 25 minutes, and in none at 15 or 20 minutes. Its published 37 of 200 selections therefore come entirely from the 25-minute cases. This is a substantial threshold dependence, not evidence that 25 minutes reflects actual family behaviour.

Candidate selection uses Wednesday 4 pm journeys. The fixed-candidate ranking checks both Wednesday 4 pm and Saturday 10 am. Journeys start at residential subzone centre points and end at MRT exits. They do not start at schools or end at a specific tuition unit. Reachable population is an access proxy, not observed enrolment or willingness to travel. The 10-minute walking fallback and 800-metre proximity fallback are held constant.

## First stage: which areas enter detailed investigation?

The same 95 commercially qualified MRT areas, 24 merit slots and 12 regional coverage slots were used for each travel limit. The 20-minute selection reproduced the published 36-area list in exactly the same order.

| Travel limit | Areas in common with the frozen 20-minute list | New areas | Frozen areas displaced | Selected areas lacking comparable competitor evidence |
|---:|---:|---:|---:|---:|
| 15 min | 34/36 | 2 | 2 | 1 |
| 20 min | 36/36 | 0 | 0 | 0 |
| 25 min | 35/36 | 1 | 1 | 1 |

| MRT area | 15-minute reach | 20-minute reach | 25-minute reach | Selected at 15 / 20 / 25 minutes |
|---|---:|---:|---:|---|
| Sengkang | 42,180 | 61,450 | 82,480 | yes / yes / yes |
| Serangoon | 5,560 | 32,570 | 88,060 | yes / yes / yes |
| Yishun | 20,600 | 27,270 | 58,250 | yes / yes / yes |
| Bukit Panjang | 9,070 | 20,080 | 23,760 | yes / yes / yes |

### Areas entering and leaving the 36-area screen

**15 minutes:** Enter: REDHILL, MACPHERSON. Leave: EUNOS, BOON KENG.

**25 minutes:** Enter: MACPHERSON. Leave: TIONG BAHRU.

## Second stage: ranking the same 36 investigated areas

For each travel limit, the original model was run at two journey times under four competition treatments and five preference profiles, giving 40 setting comparisons. These counts are not probabilities or independent trials. The finance input is identical for every area and cannot distinguish them.

| MRT area | Top-three selections at 15 min | At 20 min | At 25 min |
|---|---:|---:|---:|
| Sengkang | 40/40 | 40/40 | 40/40 |
| Serangoon | 0/40 | 0/40 | 37/40 |
| Yishun | 20/40 | 20/40 | 19/40 |
| Bukit Panjang | 10/40 | 10/40 | 3/40 |

### Highest selection counts within the fixed 36

**15 minutes:** Sengkang (40/40), Yishun (20/40), Bukit Panjang (10/40).

**20 minutes:** Sengkang (40/40), Yishun (20/40), Bukit Panjang (10/40).

**25 minutes:** Sengkang (40/40), Serangoon (37/40), Yishun (19/40), Bukit Panjang (3/40), Marsiling (1/40).

## Can the alternative 36-area lists be ranked fully?

**15 minutes:** A comparable final ranking is unavailable because 1 selected area lacks competitor coverage: MACPHERSON. No competitor count was imputed.

**25 minutes:** A comparable final ranking is unavailable because 1 selected area lacks competitor coverage: MACPHERSON. No competitor count was imputed.

## Interpretation and limits

- The 20-minute scenario is one decision assumption. The 15- and 25-minute comparisons show how dependent the candidate screen and subsequent ranking are on that assumption.
- The fixed-36 ranking is comparable across travel limits but cannot reveal the final ranking of areas left outside the original 36. The alternative-36 ranking is shown only when the same competitor protocol has covered every selected area.
- The published full model's 200 top-three counts were reproduced exactly before interpreting these subsets. The original 20-minute candidate order also reproduced exactly.
- Thresholds do not estimate actual travel preferences. Subzone-centre origins, station-exit destinations, one weekday and one weekend timestamp, and incomplete market evidence limit business interpretation.

Sources: `config/competitors/candidate_freeze.json`, the qualified-node, population-proximity and accessibility outputs it references, `reports/competitors/2026-09-18/national_completion/national-competition-summary.json`, and `reports/analysis/2026-09-18/final_decision/final-decision.json`. Full source checksums and per-area diagnostics are in the accompanying JSON.
