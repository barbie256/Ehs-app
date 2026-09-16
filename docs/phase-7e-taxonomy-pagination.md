# Bounded category discovery

Synchronization now calls `get_all_categories(per_page)`. The existing
`get_categories()` remains a single default-page request for the durable probe
and other existing callers. `get_categories_page(page, per_page)` is additive.

Only the categories endpoint traverses multiple pages. Directories and locations
retain their existing single-request behavior: their pagination contracts have
not been verified. Listing-derived fallback discovery is a possible follow-up,
not part of this fix.

## Contract and failure behavior

- Requests use GET on the fixed `/listings/categories` path, with encoded `page`
  and `per_page` parameters. Link-header destinations are never followed.
- Synchronization uses its configured listing page size for category pages:
  currently 20, with the existing 100-page limit. No limits are raised.
- Both pagination headers are required nonnegative ASCII decimal integers within
  the safe integer limit. Nonempty totals must agree with the requested page
  size and reported page count. Empty collections permit zero or one page.
- Each page must contain exactly the expected number of objects, with unique
  positive integer identities. Booleans and string identities are rejected.
- Totals/page counts must remain stable and identities must not repeat across
  pages. Category pagination always enforces the page bound, independently of
  the listing probe's reported-page-limit override.
- The complete collection is returned only after every page passes. Requests
  retain existing timeout, response-size, redirect, credential-free client,
  fixed source boundary, and bounded retry behavior. The response-size check
  remains post-download validation, not a streaming cutoff.

Taxonomy discovery runs before listing processing. A category-page failure
therefore reaches the existing controlled run-failure path before listing writes
or unseen-listing archival. Existing transaction rollback, run finalization and
advisory-lock release remain in place. The listing page counter continues to
count listing-page attempts; it does not count taxonomy requests or retries.

Discovery inserts new identities as pending with no canonical target. Existing
approved/rejected statuses and targets are unchanged by rediscovery; only name
snapshots and their update times can change. Missing identities are not deleted.
No targets are inferred from category names.

## Verification and remaining limits

Synthetic HTTPX tests cover multiple pages, single/empty collections, invalid
metadata and bounds, duplicate identities, changing totals, later-page HTTP
failures, fixed GET requests, bounded retries and controlled errors. Existing
probe regressions retain exactly four approved requests with no taxonomy
pagination. Guarded test-database checks use an outer rollback transaction and
savepoint-bound sessions, without schema creation or canonical seeding. They
check later-page pending discovery, preservation of approved/rejected targets,
repeat discovery, failure finalization, skipped archival and lock release.

Mock tests do not verify actual live category pagination support. Before a later
authorized refresh, confirm that the live endpoint honors these parameters and
the strict total/page contract. Stable totals and nonduplicated identities do
not prove a point-in-time snapshot when the upstream catalogue changes during
traversal. The unchanged directories/locations coverage limit also remains.

Migration/seed database rehearsals and legacy synchronization tests that invoke
canonical seeding are excluded from Phase 7E execution. Their synthetic source
implements the new complete-category method for interface compatibility.

## Deferred business decisions

Internet/connectivity services and banking/lending are approved in principle
for Professional Services / Internet Services and Banking & Finance respectively.
This does not create categories or approve mappings. Mixed source category 61
must not receive a blanket internet-service mapping. Applications such as MPU
remain pending for a separate decision. Category 81 is not approved by this fix.
No listing exceptions, country/currency defaults, canonical seed changes or
checksum reconciliation changes are included. Recurring synchronization remains
disabled.
