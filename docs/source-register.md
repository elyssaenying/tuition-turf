# Source register

**No sources have been verified or data acquired.** The entries below are discovery leads, not citations, confirmed datasets, or evidence that a particular provider offers the needed fields. URLs are intentionally absent until directly opened and checked. Do not cite this register as validation of a source or a finding.

## Verification requirements

For each source, maintain a stable `source_id`, title/provider, exact landing-page and data-resource URLs where applicable, resource identifier, source type, intended use, observed unit/grain, required fields, geography/boundary version, population basis, reference period, update frequency, opened/accessed timestamp, verifier, access method, licence/redistribution terms, access restrictions, extraction feasibility, limitations and verification status. Record a concise evidence note showing which content/metadata was actually inspected, including applicable section or table identifiers.

Allowed statuses are exactly `unverified`, `accessible_unconfirmed`, `verified_usable`, `verified_limited`, `unavailable` and `rejected`. `unverified` means no direct check and requires no verification timestamp. `accessible_unconfirmed` requires an opened URL and recorded verification timestamp, but the relevant content has not yet been inspected sufficiently to establish suitability. `verified_usable` and `verified_limited` require an opened URL, inspection of the relevant content or metadata, a concise evidence note and a recorded verification timestamp. `unavailable` requires a recorded access attempt and timestamp; it does not imply that content was opened. `rejected` requires a timestamp, rejection reason and a record of the evidence reviewed; when rejection is based on source content, the URL must have been opened and that content inspected. Do not silently treat an accessible page as usable data.

Directly open the original source page and relevant metadata/resource. Search snippets, generated links, secondary references and a successful HTTP response alone are insufficient. Verify that the opened content supports the intended claim and distinguish publication date, observation period and access date. Record redirects/broken links; use a clearly labelled archive only if its vintage fits the claim. A landing-page check does not imply any data file has been acquired or validated.

Later acquisition adds immutable snapshot references, checksums, retrieval parameters, schema and row counts. Public dashboard citations must resolve to verified public pages. Source reliability does not imply completeness or applicability to an individual premises. Licences must permit the intended analysis and any redistribution; register restrictions before publication.

## Unverified discovery queue

| Lead ID | Information needed | Potential authoritative or primary route to investigate | Feasibility questions | Status |
|---|---|---|---|---|
| L01 | Resident counts by age and geography | Singapore Department of Statistics / SingStat and official open-data catalogues | Single-year or grouped ages? Resident basis? Small-area availability? Suppression and vintage? | `unverified` |
| L02 | Planning-area/subzone boundaries and crosswalks | Official planning/geospatial publishers, including URA/SLA routes | Matching demographic vintage? Stable identifiers, CRS, licence and boundary changes? | `unverified` |
| L03 | Schools and public site context | Ministry of Education and official school directories | Physical locations, school levels, dates and closed/relocated sites? | `unverified` |
| L04 | Transit stations, stops and service/access information | Land Transport Authority and official geospatial/routing services | Redistribution, route-time coverage, schedules, API restrictions and mode assumptions? | `unverified` |
| L05 | Mathematics competitor brands, branches and offerings | Operators' own branch pages and level/subject schedules; independent directories for corroboration | Current physical branches? Branch-specific P1–S4 mathematics? Duplicate/closed locations? | `unverified` |
| L06 | Non-direct education-provider cluster context | Providers' own public branch pages, corroborated public directories | Scope and current physical presence? Can direct rivals be separated consistently? | `unverified` |
| L07 | Intended-use permission and premises suitability | Current official premises-use guidance and premises-specific documented approvals | Which authorities/evidence apply to the intended activity/unit? How can current permission be confirmed? | `unverified` |
| L08 | Commercial premises availability and occupancy costs | Primary landlord/agent listings, documented terms and relevant official market evidence | Asking versus effective rent? Unit/area, service charges, use constraints, observation date and duplicate listings? | `unverified` |
| L09 | Fees, delivery costs and opening costs | Public operator fee schedules; documented supplier/landlord evidence; voluntarily supplied operator inputs later | Billing period, discounts, contact hours, class cost steps, fit-out/deposits and comparability? | `unverified` |
| L10 | Tuition participation/affordability context | Official surveys/statistics if suitable, with transparent methodological review | Relevant age/geography/subject? Can national evidence support only broad scenarios? | `unverified` |
| L11 | Existing network and cannibalisation, expansion case only | Authorised operator-provided aggregate records, if available later | Coverage, consent/access, aggregation, reliable pupil origin/catchment and baseline contribution? | `unverified` |

Lead IDs are research tasks, not verified `source_id` values. One lead may yield several sources, or no usable source. Register failed searches and substitutes; never fabricate URLs, premises, operating assumptions or validation. If a critical source is unavailable, document a reduced-scope method or block the affected conclusion rather than silently substituting invented values.

## Refresh and conflict handling

Set evidence-specific recency thresholds after inspecting update cadences. Branch status, available units and permission checks need review close to recommendation time; demographics may have a different stable release cycle. Record the chosen tolerances in the decision log. Preserve conflicting evidence and the reason for any adjudication. An unresolved contradiction remains a quality issue and, where material to eligibility or comparison, a blocker.
