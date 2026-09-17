# National accessibility routing plan

Run ID: `routing_plan_d17bea62d5e154ae`  
Status: **planning complete; execution not authorised**

- Origins: 332 MP2019 subzone centroids
- Destinations: closest preserved station exit for each of 146 current MRT-area candidates
- Scenarios: 2 (weekday primary and weekend comparison)
- Planned primary PT requests: 96,944
- Theoretical PT-only duration at the conservative 240/minute cap: 6.7 hours
- Missing PT results would add walking-fallback requests, so actual execution would take longer.
- No authentication, route or other network request was made by this planning run.

## Required approval

The approved main setting is `maxWalkDistance=500` metres. A bounded same-route comparison at 300, 500, 1000 metres is authorised.

Only the bounded comparison is authorised. National execution remains unapproved.
The route client must use resumable redacted caching, safe token handling, conservative pacing and immediate stop controls.
