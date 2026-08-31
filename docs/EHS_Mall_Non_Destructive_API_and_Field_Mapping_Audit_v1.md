# EHS Mall Non-Destructive API and Field-Mapping Audit

**Status:** Version 1 — read-only audit complete  
**Audit date:** 31 August 2026  
**Production system:** [ehsmall.com](https://ehsmall.com/)  
**Related baseline:** `EHS_Mall_MVP_Architecture_and_Database_Plan.md`

## 1. Audit objective

Determine which Directorist capabilities are visible on the live EHS Mall website, map the public listing response into the proposed FastAPI/PostgreSQL model, identify data-quality and security gaps, and prepare safe test data without changing the production website.

## 2. Non-destructive rules followed

The audit used only:

- Public HTTP `GET` requests
- Public WordPress route metadata
- Offline inspection of the supplied WordPress archive
- Counts, schemas and aggregate observations

The audit did **not**:

- Log in to WordPress
- Use supplied database credentials
- Open or query the migration backup database
- Create, update or delete listings
- Submit forms, reviews, favourites, enquiries, orders or payments
- Upload media
- Trigger password-reset operations
- Call administrative write routes
- Extract or publish personal contact values
- Change website files, plugins, settings or database records

## 3. Executive result

The live site provides enough public read functionality to build the proposed read-only catalogue MVP behind a FastAPI adapter.

Confirmed live observations:

| Item | Observed result |
|---|---:|
| Published listings | 23 |
| Directorist directories | 1 |
| Categories | 35 |
| Locations | 1 |
| Public reviews returned | 0 |
| Listings with images | 23 |
| Listings with a non-empty email field | 20 |
| Listings with a non-empty phone field | 18 |
| Listings with a non-empty website field | 17 |
| Listings marked contact-hidden | 0 |
| Listings using a visible price | 9 by pricing type; 8 with a non-zero price |
| Featured listings | 0 |
| Listings with ratings | 0 |

All 23 observed listings had `status = publish`, used Directorist directory ID `3`, and were assigned to the single location `Kampala` (ID `51`).

### Audit conclusion

**Proceed with the read-only adapter and synchronized catalogue prototype.** Do not yet implement shared login, WordPress favourites, reviews, vendor writes, checkout or payments. Those functions require a staging environment, permission tests and explicit security review.

## 4. Live technology and route inventory

The supplied archive and live route directory confirm:

- WordPress 7.0 code in the supplied archive
- Directorist 8.8.3 in the supplied archive
- Directorist namespaces `directorist/v1` and `directorist/v2` registered live
- Public WordPress REST route discovery enabled
- Apache serving the live website

### 4.1 Confirmed live public `GET` routes

| Route | Result | MVP use |
|---|---|---|
| `/directorist/v1/listings` | `200` | Primary public listing source |
| `/directorist/v1/listings/{id}` | Registered; individual route available | Detail refresh candidate |
| `/directorist/v1/directories` | `200` | Directory metadata |
| `/directorist/v1/listings/categories` | `200` | Category synchronization |
| `/directorist/v1/listings/locations` | `200` | Location synchronization |
| `/directorist/v1/listings/tags` | `200` | Optional tags |
| `/directorist/v1/listings/reviews` | `200`, empty array | Future read-only reviews after moderation policy |
| `/directorist/v1/pages` | `200` | Internal Directorist page references; not app content source yet |
| `/directorist/v2/listings` | `200` | Candidate future schema; custom fields nested under `fields` |
| `/directorist/v1/users` | `200` in minimal probe | Do not integrate until public-field exposure is reviewed |

### 4.2 Confirmed authentication boundaries

| Route | Minimal `GET` result | Decision |
|---|---|---|
| `/directorist/v1/orders` | `401` | Correctly requires authentication; deferred |
| `/directorist/v1/admin/orders` | `401` | Correctly requires authentication; deferred |
| `/directorist/v1/plans` | `400` in unauthenticated minimal request | Configuration/required input needs staging review |

### 4.3 Registered write-capable routes not called

The live route directory advertises operations for:

- Creating listings, directories, categories, locations, tags and users
- Updating and deleting resources
- Listing actions/contact messages
- User favourites
- Password reset and change
- Temporary media uploads
- Checkout and retry payment
- Orders, payments and refunds
- Admin plugin installation

Their presence is not authorization to use them. Every write capability remains outside the MVP audit until it is tested with a restricted account on staging.

## 5. Public listings API behavior

### 5.1 Pagination and headers

The listing collection returned:

- `X-WP-Total: 23`
- `X-WP-TotalPages` based on `per_page`
- A `Link` header for the next page when applicable
- `Allow: GET` on the observed collection response

The synchronization client should read the total-page header, follow bounded pagination and stop when the advertised page count is reached.

### 5.2 Registered query parameters

The live route schema advertises these useful read filters:

- `page`, `per_page`, `offset`
- `search`
- `include`, `exclude`
- `author`
- `directory`
- `categories`, `locations`, `tags`
- `min_price`, `max_price`, `price_range`
- `rating`
- `featured`
- `status`
- `orderby`, `order`
- `latitude`, `longitude`, `radius`

It also advertises listing fields on create operations. The app will not use those write capabilities during MVP.

### 5.3 Safe filter tests

| Test | Result | Interpretation |
|---|---:|---|
| `search=cement` | 5 listings | Full-text search is broader than category matching |
| `categories=29` | 2 listings | Category filtering works for Cement |
| `locations=51` | 23 listings | Location filtering works; all current data is Kampala |
| `max_price=1000000` | 7 listings | Maximum-price filtering produced a plausible subset |
| `min_price=1` | 0 listings | Unexpected; do not trust minimum-price filtering yet |
| `rating=1` | 0 listings | Consistent with all current listings having zero ratings |
| `orderby=date&order=desc` | Returned newest IDs first | Date sorting works in observed sample |
| `orderby=price&order=asc` | Returned ascending priced sample | Price ordering appears usable but needs zero/unpriced tests |

The FastAPI adapter should implement its own validated filtering against the synchronized PostgreSQL mirror. It may pass supported filters upstream for efficiency, but correctness must not depend exclusively on undocumented Directorist behavior.

## 6. Existing catalogue structure

### 6.1 Directorist directory

| ID | Name | Slug | Published listings |
|---:|---|---|---:|
| 3 | Business | `business` | 23 |

Directorist “directory” does not currently represent the four proposed EHS marketplaces. All content is in one generic Business directory.

### 6.2 Location structure

| ID | Name | Parent | Published listings |
|---:|---|---:|---:|
| 51 | Kampala | None | 23 |

The current location taxonomy is too shallow for an African marketplace. The new platform should support country → region/district → city/area hierarchy, while preserving Directorist location IDs during coexistence.

### 6.3 Category hierarchy

| Existing root | Current children |
|---|---|
| Marketplace | Appliances; Building Materials; Cement; Doors; Energy Solutions; Gardening & Landscaping; Interior Decor; Joinery; Nursery & Plants; Office Supplies; Plumbing; Roofing; Steel; Timber |
| Properties | Apartments; Commercial Properties; Land and Plots; Rentals |
| Home and Interior | Furniture; Kitchen; Lighting; Sanitary Ware; Tiles |
| Services | Architects; Engineers; Interior Designers; Internet Solutions; Movers; Property Managers |
| Shopping | None observed |
| Homes | None observed |

### 6.4 Required category cleanup before migration

- The proposed **Construction Marketplace** does not exist as a root; construction items currently sit under `Marketplace`.
- `Interior Decor` and `Appliances` are under `Marketplace` rather than `Home and Interior`.
- `Building Materials` and `Cement` are siblings even though Cement could be a child of Building Materials.
- `Shopping` and `Homes` appear to be unused legacy roots.
- `Internet Solutions` is under Services but is not part of the initial professional-services list.
- A category can carry listings while its root has a count that only represents direct assignments, not the descendant total.
- Category names containing HTML entities must be decoded safely for display.

The MVP adapter should map existing categories without rewriting WordPress. EHS stakeholders should approve a canonical taxonomy separately.

## 7. Directorist v1 listing field map

### 7.1 Identity and lifecycle

| Directorist field | Observed type | EHS target | Transformation |
|---|---|---|---|
| `id` | number | `listings.external_id` | Required; store with `source_system=directorist` |
| `name` | string | `listings.title` | Trim; decode safe entities |
| `slug` | string | source metadata | Validate; not the EHS UUID |
| `permalink` | string | `listings.source_url` | Allow only approved HTTPS host |
| `status` | string | `listings.status` | `publish → active`; other values unavailable/archived by policy |
| `date_created_gmt` | string | source created time | Prefer GMT; parse strictly |
| `date_modified_gmt` | string | `source_modified_at` | Prefer GMT; sync cursor/checksum input |
| `date_expired` | string | source expiry | Empty → null |
| `never_expired` | boolean | source metadata | Preserve |
| `new`, `popular`, `featured` | boolean | listing flags | Preserve as source flags |
| `menu_order` | number | source sort order | Optional |

### 7.2 Classification and ownership

| Directorist field | Observed type | EHS target | Transformation |
|---|---|---|---|
| `directory` | number | source directory ID | Map through integration table |
| `categories` | array | listing-category relations | Upsert category by external ID; allow many |
| `locations` | array | listing-location relations | Upsert by external ID; choose primary location by policy |
| `tags` | array | listing tags | Optional, sanitized |
| `author` | number | `vendors.external_owner_id` | Never expose raw author ID to app |
| `plan` | number | source metadata | Do not interpret as vendor verification |
| `related_ids` | array | source relations | Optional; validate IDs |

### 7.3 Descriptive content

| Directorist field | Observed type | EHS target | Transformation |
|---|---|---|---|
| `description` | string/HTML | `listings.description` | Sanitize with strict allowlist |
| `short_description` | string/HTML | `listings.summary` | Sanitize and length-limit |
| `tagline` | string | listing attribute | Trim and length-limit |
| `address` | string | listing/location display field | Normalize; do not treat as verified geocoding |
| `zip` | string | address attribute | Optional |
| `latitude`, `longitude` | numeric strings | typed decimal coordinates | Parse/range-check; blank → null |
| `map_hidden` | boolean | visibility rule | Suppress map coordinates when true |
| `video_url` | string | listing media link | Approved HTTPS hosts only |

### 7.4 Pricing

| Directorist field | Observed type | EHS target | Transformation |
|---|---|---|---|
| `price` | number | `listings.price_amount` | Use decimal, not binary float; zero may mean unspecified |
| `pricing_type` | string | `listings.pricing_type` | Blank → contact/unspecified by approved policy |
| `price_range` | string | listing pricing attribute | Normalize only after business rules are defined |

The response does not expose a dedicated currency field. The app must not assume that every number is UGX until EHS approves a current currency rule or the website supplies currency metadata.

### 7.5 Contact and privacy

| Directorist field | Observed type | EHS target | Transformation |
|---|---|---|---|
| `owner_contact_hidden` | boolean | contact visibility | Authoritative visibility gate |
| `email` | string | `listing_contacts.public_email` | Store/display only when allowed; validate |
| `phone`, `phone_2` | string | public phone records | Normalize for search/contact; retain display form safely |
| `fax` | string | optional contact | Usually omit from app MVP |
| `website` | string | public website | HTTPS/domain validation |
| `social_links` | null in current data | optional social contacts | Validate provider and URL if later present |

Although all 23 observed listings returned `owner_contact_hidden=false`, the adapter must enforce this field for every record and must not send all contacts to the AI model.

### 7.6 Media

| Directorist field | Observed type | EHS target | Transformation |
|---|---|---|---|
| `images` | array | `listing_media` | Validate URL, preserve order and alt text |
| image `id` | number | media external ID | Unique within source context |
| image `src` | string | source URL | Proxy/cache decision later; HTTPS allowlist |
| image `alt` | string | alt text | Sanitize; create fallback only when necessary |
| image `position` | number | sort order | Preserve |
| image timestamps | string | source metadata | Strict parse |

Every current listing had at least one image. The app must still handle missing or failed images with an EHS placeholder.

### 7.7 Ratings and analytics

| Directorist field | Observed type | EHS target | Transformation |
|---|---|---|---|
| `reviews_allowed` | boolean | source policy | Preserve |
| `average_rating` | number | listing rating summary | Treat zero with zero count as “not rated” |
| `rating_count` | number | listing rating count | Preserve |
| `views_count` | number | source analytics | Do not equate with app views |

### 7.8 Fields to discard from the normalized mobile response

- `yoast_head`
- `yoast_head_json`
- Raw `_links` except internally useful source references
- Internal author and plan identifiers
- Hidden contacts
- Unused WordPress/plugin metadata

These fields add payload size and may expose implementation details without improving the app experience.

## 8. Directorist v2 assessment

The v2 listing route is live and returns core metadata plus a nested `fields` object. Observed field keys included:

- `title`, `description`
- `categories`, `locations`, `tags`
- `address`
- `price`, `price_type`, `price_range`
- `email`, `phone`, `website`
- `listing_img`, `videourl`
- A custom textarea field

V2 may better support directory-specific custom fields, but V1 currently provides a flatter, easier read model. The MVP adapter should start with V1 behind an interface so V2 can be evaluated without changing the mobile API.

## 9. Security and privacy findings

### Finding SEC-01 — Sensitive archive

**Severity:** High if shared outside the authorized team  
**Evidence:** The ZIP contains `wp-config.php` and a `.wpress` full-site backup.  
**Risk:** Database credentials, WordPress salts, user records and site content may be disclosed.  
**Action:** Store privately; never commit to Git; rotate secrets if the archive was exposed publicly; use a sanitized copy for development.

### Finding SEC-02 — Public user endpoint schema

**Severity:** Medium pending configuration review  
**Evidence:** A minimal unauthenticated `GET /directorist/v1/users?per_page=1` returned `200`. Its public object schema includes email, phone, address, username, roles and social-link fields. The single sampled record had empty sensitive contact/role values.  
**Risk:** Future or other records could expose personal data if populated, even when the current minimal sample is blank.  
**Action:** Website developer should restrict the user collection route or filter public responses to an explicit safe field allowlist. Do not integrate this route into the app until resolved.

### Finding SEC-03 — Listing contacts broadly public

**Severity:** Informational/business-policy decision  
**Evidence:** Most listings contain contact fields and all observed visibility flags allowed contact display.  
**Risk:** Scraping, spam and unnecessary AI exposure.  
**Action:** Confirm these are intentional business contacts; rate-limit app contact retrieval; reveal contacts only under approved UX rules; never include the complete raw listing response in model prompts.

### Finding SEC-04 — Write routes advertised publicly

**Severity:** Not a vulnerability by itself  
**Evidence:** REST discovery advertises numerous POST/PUT/PATCH/DELETE routes.  
**Risk:** Incorrect permission callbacks or credential handling could enable unauthorized changes.  
**Action:** Test authorization on staging with guest, customer, vendor and administrator accounts before any mobile write integration.

## 10. Proposed normalized app listing response

The mobile app should receive a compact EHS-owned response similar to:

```json
{
  "id": "ehs-uuid",
  "title": "Listing title",
  "marketplace": {"code": "construction", "name": "Construction"},
  "categories": [{"id": "ehs-category-uuid", "name": "Cement"}],
  "location": {"id": "ehs-location-uuid", "name": "Kampala"},
  "summary": "Sanitized short description",
  "pricing": {"amount": "50000.00", "currency": "UGX", "type": "fixed"},
  "images": [{"url": "approved-url", "alt": "Listing image"}],
  "rating": null,
  "featured": false,
  "contact_available": true,
  "source_url": "https://ehsmall.com/directory/example/",
  "source_modified_at": "2026-08-31T13:24:02Z"
}
```

Currency must remain null/unspecified until the EHS currency rule is confirmed; `UGX` above is illustrative, not an audited source value.

## 11. Sanitized fixture

`EHS_Mall_Directorist_Sanitized_Listing_Fixture_v1.json` accompanies this audit.

It:

- Preserves the observed Directorist v1 field names and representative types
- Uses synthetic IDs, text, URLs and coordinates
- Contains no website passwords, tokens or database secrets
- Contains no real vendor/customer email, phone or address
- Can be committed to the future application repository under a test-fixtures directory

## 12. Required changes to the architecture baseline

The Version 1 architecture remains valid with these refinements:

1. Start the adapter with Directorist v1, but hide it behind a version-independent interface.
2. Add explicit source tables/columns for Directorist directory, category, location and owner IDs.
3. Use a many-to-many listing-category relation; a listing can have multiple categories.
4. Use typed decimal pricing with nullable currency.
5. Add an HTML sanitization step before persistence and another safe-rendering layer in the app.
6. Add an explicit `contact_available` projection instead of returning contact fields on collection screens.
7. Add a canonical taxonomy mapping table rather than rewriting website categories during MVP.
8. Treat the public users endpoint as prohibited until reviewed.
9. Add sync monitoring for total pages, counts, checksums, invalid records and stale-source behavior.
10. Test all integration behavior against fixtures first and staging second.

## 13. Remaining decisions for EHS and the website developer

1. Is the archive from production, staging or a developer’s local copy?
2. Has this sensitive ZIP ever been stored in a public repository or public download location?
3. Are listing email and phone fields intentionally public business contacts?
4. What currency does the current `price` field use, and can listings use different currencies?
5. Should `price=0` mean free, unknown or “contact for price”?
6. Which existing categories map to the four new marketplace roots?
7. Should unused roots (`Shopping`, `Homes`) be retained, remapped or retired later?
8. Can the developer provide a staging copy for authentication and permission testing?
9. Who receives app enquiries during the MVP?
10. Will users initially create EHS app accounts, or must they eventually share WordPress accounts?

## 14. Read-only audit verdict

| Area | Verdict |
|---|---|
| Public listing retrieval | PASS |
| Pagination | PASS |
| Keyword search | PASS |
| Category filtering | PASS |
| Location filtering | PASS, but current taxonomy has one location |
| Maximum-price filtering | Provisional PASS |
| Minimum-price filtering | FAIL/needs investigation |
| Date sorting | PASS |
| Price sorting | Provisional PASS |
| Category taxonomy readiness | NEEDS MAPPING |
| Currency readiness | BLOCKED BY MISSING SOURCE FIELD/RULE |
| Public user-data safety | NEEDS WEBSITE REVIEW |
| Authenticated writes | NOT TESTED BY DESIGN |
| Orders/payments | DEFERRED |
| Read-only MVP feasibility | PASS |

## 15. Next engineering step

Do not scaffold the entire application yet. First create and approve a **Phase 1 Repository and Backend Foundation Specification** covering:

- Repository layout
- Environment separation
- FastAPI module boundaries
- Initial Alembic migrations
- Directorist adapter interface
- Synchronization service and failure rules
- Pydantic source/normalized schemas
- Authentication boundary
- Audit logging
- Test strategy using the sanitized fixture
- Explicit prohibition of WordPress production writes

After that specification is approved, Codex can safely scaffold Phase 1 in small, verifiable steps.

