# Batch B — Buyer dashboard and marketplace

Starting commit: `5ec35c8ca913dab23507855b4b3a2c71b5df92a9`, branch `feature/frontend-buyer-vendor-integration`.

## Approved source

Read the local approved Figma Make `App.tsx` components AppHeader, PageShell, BuyerHome, SearchPage, ProductCard, ProductDetail and related vendor/profile routing; styling from `src/index.css`. The implementation uses the source's DM Sans/Manrope typography, green palette, dark dashboard hero, desktop sidebar, mobile drawer, eleven category tiles, search/filter column, cards and two-column detail/gallery layout. SVG icons retain the source paths.

## Screens and behavior

- New `/buyer/dashboard`: sample Buyer overview; real GET search navigation to `/marketplace?q=...`; category links; nearby sample cards and safety link.
- `/marketplace`: adapted to SearchPage. Existing six fixture IDs and search across title/description/category/location/vendor are retained, along with category, location, condition, min/max price, ascending/descending price and newest sorting, invalid bounds, empty state and clear filters. Case-insensitive category URLs remain supported. Dashboard search queries now initialize search input/results.
- `/listings/[id]`: source ProductDetail composition, working sample thumbnails, all prior IDs, browser-local metadata and IndexedDB photo loading, price/unit/quantity/description, vendor/map links and existing ContactVendorForm demo below the detail section, preserving the source mobile gallery-to-title reading order.
- `/vendors/[slug]`: minimal fixture lookup expansion so designer sample vendors resolve. No public API profile is fabricated; fixture verification flags are labelled as sample-only.
- Primary sidebar/mobile links are real URLs. Orders, Messages, Profile, Settings and Notifications use explicit unavailable-data notices through `/buyer/dashboard?view=...`. No fake orders, unread counts, ratings, payments, authenticated sessions or live vendor verification are shown.
- Drawer closes on navigation/Escape/backdrop, traps keyboard focus, restores trigger focus and locks background scroll.

## Presentation data and exact assets

`src/lib/data/buyer-fixtures.ts` adds the seven original designer sample listings to the existing six; it does not replace `src/lib/data/listings.ts` or change existing IDs. Designer sample vendors have no asserted verification. The optional verification filter applies only to clearly labelled legacy fixture flags, not live vendor status.

All fourteen exact source image URLs and their local paths are in `public/images/buyer/SOURCES.json`. The BuyerHome category map reuses source image keys exactly, including the separate 400px Scrap Metal URL. No exported PNG chronology was inferred. New source galleries repeat the item image and use `parts` and `mechanic` exactly as the prototype, labelled as presentation images rather than evidence of stock. Legacy category illustrations retain their labels and browser-local photos retain priority.

No remote image request is required by the implemented Buyer views. External map links are user-initiated and use fixture/local listing locations, not private API vendor addresses.

## Authoritative backend consulted — read only

Workspace: `/home/sallieakpan/Desktop/scrapmart-backend/backend`, branch `feature/database-models`, HEAD `f446f2f46de0040ebffd2df0e2870841d9468b1c`.

Files: `app/api/v1/marketplace.py`, `buyer_account.py`; `app/modules/listings/schemas.py` and `service.py`; `app/modules/auth/vendor_authorization.py`. Prior auth contracts remain documented in Batch A.

- Public `GET /api/v1/listings` accepts bounded `limit`/`cursor`, `q`, `category_id` (UUID), `location`, canonical `condition`, decimal-string `min_price`/`max_price`, `verified_only` and `sort`. Only `recent` sorting is accepted. Results contain `listings` and `next_cursor`.
- `GET /api/v1/listings/{listing_id}` requires a UUID, returns a single public listing, and uses a not-found error for unavailable items. Presentation IDs are not API IDs and must never be sent to that endpoint.
- Public records must be active with stock, stored photos, active category/user and approved Vendor evidence. `verified_only=false` does not bypass the service's approved-vendor public query.
- DTOs include title, category_id, description, decimal-string price/quantity/available_quantity, price_type, is_negotiable, condition, quantity_unit, public location fields/visibility/directions flags, status/currency/timestamps, photos (id/url/position/width/height), nested category (id/name/slug), and vendor (business_name/shop_location/verified). Vendor location is the listing's public summary, not the private shop address. No ratings, sales totals or arbitrary public Vendor profile endpoint were found in these contracts.
- `GET /api/v1/categories` returns active categories plus `next_cursor`, with bounded `limit` and UUID `after` pagination. Local category labels are presentation taxonomy, not invented canonical UUIDs.
- Conditions: `good_condition`, `used`, `faulty`, `damaged`, `for_parts`; units: `pieces`, `kilograms`, `tonnes`, `bundles`. Legacy fixture `Mixed`, `kg`, etc. are not silently treated as API enum values.
- Buyer identity is read through authenticated `/api/v1/auth/me`; live capabilities are discovered through `/api/v1/auth/capabilities`. No caller-selected identity or browser flag grants permissions. Vendor listing mutations require actual approved Vendor authorization. Orders/messages require their own authenticated contracts and are not implemented here.

## Live versus demo boundary

This batch performs no staging API calls and creates no sessions. All displayed listing/profile data is labelled presentation data. Client-side price sorting, category labels and verification-flag filtering remain local features and are not advertised as server capabilities. Future integration must add explicit DTO/enum/decimal/category mapping, cursor handling and backend session/CSRF authorization. It must not serialize presentation objects directly or invent vendor/rating endpoints.

Contact, Order and Report actions never claim delivery or success. Contact retains the original explicit demo message; Order and Report explain that no operation was created. No auth or landing source was changed.

## Review artifacts

Local preview: `http://localhost:3106/buyer/dashboard` and `http://localhost:3106/marketplace`.

Screenshots: `/tmp/scrapmart-buyer-{dashboard|marketplace|detail|legacy-detail}-{desktop|mobile}.png`.

No commits, pushes, deployments, backend/database changes, PRD edits or designer reference changes are authorized for this batch.

## Final validation

- `npm run lint`: passed without warnings.
- `npm run build -- --webpack`: passed, including TypeScript and route generation.
- Dashboard search/category links; all thirteen fixtures; title/vendor/location search; legacy category URLs; category/location/condition/min/max price filters; invalid bounds; both price sorts; fixture verification switch; empty state and clear filters passed browser checks.
- Detail gallery selection, source and legacy IDs, sample vendor profile, browser-local listing resolution, missing listing state and existing contact demo passed. Order/report actions explicitly report that nothing was created/submitted.
- Dashboard, marketplace, new detail and legacy detail fit 320, 390, 768, 1024 and 1440 pixels. An oversized detail chevron found during testing was corrected; final detail checks pass all widths.
- Mobile navigation opens, locks background scrolling, closes on Escape, restores trigger focus and follows its Orders link to an unavailable-data notice. Messages navigation resolves.
- Landing and all Batch A route variants checked return 200; landing retains four hero images and auth password visibility works.
- No browser runtime exceptions, referenced image failures, API mutations or fake-session writes were observed.

The completed landing page, Batch A source, shared header/global styles, password validation, original listing fixtures, backend/PRD and designer reference are unchanged. Nothing is staged or committed for Batch B.
