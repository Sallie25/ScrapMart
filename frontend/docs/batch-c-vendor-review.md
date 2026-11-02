# Batch C — Vendor dashboard and listing management

Source: read-only Figma Make `src/App.tsx`: AppHeader (line 161), VendorDashboard (509), AddListing (514), BulkUpload (522), MyListings (528), and `src/index.css` tokens. No PNG chronology was used.

## Route mapping

- `/vendor/dashboard`: approved dark-green welcome, four overview cards, recent inventory and shop actions. Sample identity is explicitly unverified; unavailable order/sales/message totals are dashes.
- `/vendor/listings`: source status tabs and listing rows; edit, pause/activate, mark sold and remove operate on labelled in-memory fixtures only. Reload/navigation resets them.
- `/vendor/listings/new`: source rounded white card, photo region, item name, category/price, description, condition/quantity, location. Existing shop-name/unit fields, optional real local photo upload, validation and browser save remain. No live publication.
- `/vendor/listings?view=local`: preserved browser inventory, detail links and confirmed removal with IndexedDB photo cleanup. Prior dashboard component is retained as `vendor-local-listings.tsx`.
- `/vendor/dashboard?view=bulk`: source bulk-upload presentation and three-image review; editable names and row removal. No upload/publish claim or fake extraction from photos.
- `?view=orders`, `messages`, `profile`, `settings`, `location`, `notifications`: navigable, explicit unavailable-service notices with return links.

Desktop sidebar and mobile drawer use the established workspace navigation pattern with focus handling, Escape, focus trapping and scroll lock. Vendor CSS/font variables are separately scoped; existing Buyer/landing/auth files are unchanged.

## Backend contracts inspected (read-only)

Authoritative workspace: `/home/sallieakpan/Desktop/scrapmart-backend/backend`.

- `app/api/v1/vendor_account.py`: GET `/api/v1/auth/vendor/me`, GET `/api/v1/auth/capabilities`; authenticated identity, not client fixture identity.
- `vendor_onboarding.py`, `modules/vendors/onboarding_schemas.py`: GET/PATCH `/api/v1/auth/vendor/onboarding`; business_name, shop_location, shop_address, response verification_status. No client-controlled approval. Profile statuses pending/approved/rejected/suspended (`modules/auth/vendor_authorization.py`). Selling requires current approved evidence, not a stale claim.
- `marketplace.py`, `modules/listings/schemas.py`, `modules/listings/service.py`: GET/POST `/api/v1/vendor/listings`, GET/PATCH `/{id}`, POST `/{id}/publish`, `/pause`, `/sold`, archive operation. Create produces draft. Edit only draft/active/inactive. Publication requires complete fields, active category, stored photo and public location consent. All Vendor operations require authorization and ownership; forbidden/conflict/invalid/unavailable responses are 403/409/422/503.
- GET `/api/v1/categories`: backend category UUIDs must replace display strings during real integration. Schema uses decimal strings (price precision 2, quantity 3), conditions good_condition/used/faulty/damaged/for_parts, units pieces/kilograms/tonnes/bundles. Local legacy fields are not API payloads.
- `orders.py`: authenticated `/api/v1/vendor/orders` and order transitions; Pay on Delivery, approved Vendor access.
- `messaging.py`: authenticated `/api/v1/conversations`, history, send and read; conversation membership and approved Vendor evidence enforced.
- `buyer_sessions.py` session_guard calls Origin/CSRF checks for mutations. No requests, tokens, fake sessions or backend changes added in Batch C.

## Assets and boundaries

Reuses exact already-downloaded designer images under `public/images/buyer/`, with original URLs documented in `public/images/buyer/SOURCES.json`. Overview uses the initial designer listing fixtures; bulk review uses engine.jpg, wires.jpg and metal.jpg in the source's slots. Local user photos remain browser-only. Existing DM Sans and Manrope fonts and reusable icon component are used. No new external image URLs or dependency changes.

Live backend features remain disconnected. Sample statuses, edit results and bulk review are never represented as actual stock, sales, verification or sent messages. Local demo listing save/delete remain functional and explicitly browser-only.

## Validation and review

Passed: `npm run lint`, `npm run build -- --webpack` (including TypeScript), `node --test tests/auth-passwords.test.mjs`, `git diff --check`.

Headless Edge checks: Vendor overview/listings/add/bulk/orders/messages at 1440/390px and overflow checks at 320/768px; images loaded; mobile drawer opens/closes/restores scroll and navigates; empty status filter, sample pause/edit/sold; three-photo bulk review and removal; required-field and negative-price validation; actual local photo preview, local save, inventory and confirmed deletion. Existing landing, Buyer/Vendor signup, login, Buyer dashboard, marketplace and listing detail loaded. No browser runtime exceptions or mutation API requests.

Preview: `http://localhost:3108/vendor/dashboard`.
Screenshots: `/tmp/scrapmart-batch-c-{dashboard,listings,add,bulk,bulk-review,orders,messages}-{desktop,mobile}.png`.

Intentional differences from prototype: truthful sample/unverified labels replace automatic approval and fabricated sales/message totals; sample actions do not publish; native accessible photo chooser and optional local photo behavior are retained; extra shop-name/unit fields preserve existing functionality; bulk publishing, account settings, location, verification, orders and messages lead to explicit unavailable states. No backend/database or designer files changed; PRD checksum preserved. No commit, push or deployment.
