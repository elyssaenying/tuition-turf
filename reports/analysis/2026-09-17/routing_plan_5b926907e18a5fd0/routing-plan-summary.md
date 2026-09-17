# National accessibility routing plan

Run ID: `routing_plan_5b926907e18a5fd0`  
Status: **planning complete; execution not authorised**

- Origins: 332 MP2019 subzone centroids
- Destinations: closest preserved station exit for each of 146 current MRT-area candidates
- Scenarios: 2 (weekday primary and weekend comparison)
- Planned primary PT requests: 96,944
- Theoretical PT-only duration at the conservative 240/minute cap: 6.7 hours
- Missing PT results would add walking-fallback requests, so actual execution would take longer.
- No authentication, route or other network request was made by this planning run.

## Required approval

Approve or change `maxWalkDistance=1000` metres. The proposal inherits the value used in the successful fixed preflight; it was not frozen by D40.

Before execution, the route client must support resumable redacted caching, safe token handling, conservative pacing, retry-free handling of authentication errors, bounded retry/backoff for 429/transport failures, and immediate stop controls.
