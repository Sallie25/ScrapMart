# Marketplace design correction and buyer action boundary

## Reference and scope

Restored the sidebar-based Buyer marketplace geometry from checkpoint `0fb6e37af284bc5995fc71536b2fa0fb30b02346` without reverting Git or replacing existing work. No screenshot attachments were available in this turn; the earlier committed implementation supplied the layout reference. Existing Buyer fonts, 256px sidebar, rounded cards, filter panel, card proportions, spacing and responsive grid retained. Public navigation is Home, Marketplace, How it works and Log in. No Categories navigation item or desktop top navigation duplication. Mobile drawer retains focus management, Escape, focus trap, overlay dismissal and scroll locking. Authenticated workspace navigation remains unchanged.

## Existing image inspection and mapping

Inspected actual legacy image contents in `/tmp/scrapmart-old-media-review.png`, not just filenames. `src/lib/marketplace/legacy-photos.ts` explicitly maps only:

| Listing ID | Existing image | Observed relevance |
| --- | --- | --- |
| demo-copper-wire | /images/category-copper.jpg | Bare copper wire |
| listing-003 | /images/category-copper.jpg | Representative copper-wire material; not the actual offcut lot |
| demo-metal-lot | /images/buyer/metal.jpg | Mixed discarded metal components |
| demo-clothes | /images/buyer/clothes.jpg | Clothing on racks; illustrative, not evidence of the seller's stock or condition |
| listing-001 | /images/category-aluminium.jpg | Crushed beverage cans representing aluminium scrap |
| listing-005 | /images/category-iron.jpg | Rusted ferrous beams and sections |

All legacy images visibly say “Illustrative image · Not seller inventory”. Original files are reused, not replaced. Next Image provides responsive sizing. No Nigerian location claim is made. Existing buyer SOURCES.json records Unsplash CDN URLs for mixed metal/clothing; root legacy files do not have complete creator/licence provenance records. This batch does not establish new licensing clearance. These are previously present presentation assets reused under the owner's explicit design correction; external publication rights remain a provenance gap.

Seven fixture records lack a suitable legacy image: Toyota Camry Engine, Honda Accord Engine, Mixed Machinery Parts, Used Generator Engine, Used Plastic Bottles, Used Cardboard Bundles and Faulty Electric Motors. They are excluded from marketplace results, not deleted. Existing approved generated imagery remains available in landing, categories, Buyer workspace and Vendor workspace; it is not used to make these excluded marketplace listings appear photographed. The branded legacy plastic image has uncertain provenance and is not restored. No repair photos or padded galleries restored.

Valid decoded browser-uploaded photos retain priority and can make an otherwise excluded existing fixture visible. Counts are derived after image eligibility, search, filters and sort. All listing records and direct details remain intact. The current marketplace still uses the existing presentation collection, not live API inventory. Browser-local storage is media/demo data only, never proof of login.

## Buyer actions

Both Contact vendor and Order item link to `/login?role=buyer&returnTo=...`. The return path must match `/listings/{safe-id}?intent=contact|order`; external origins, traversal, extra parameters and unknown intents are rejected. Login validates inbound return destinations independently and offers a safe Return to item link. The login remains explicitly non-authenticating: no automatic redirect after demo form validation and no automatic action execution. Listing details retain a visible sign-in-required/unavailable notice instead of the message-submission form.

There are no frontend order/message API handlers or authenticated proxies. No calls to real order/message endpoints are introduced, and no demo listing IDs are transmitted to them. Read-only inspection confirms FastAPI order creation and conversation initiation still require bearer access claims and backend authorization; POST guards also require Origin/CSRF. No claim is made that frontend private dashboards are now protected. Future real login must revalidate the return intent, require Buyer capability and a real backend listing UUID before enabling a deliberate action; the retained intent is not an authorization grant or instruction to automatically purchase/send.

## Validation

Existing lint, explicit TypeScript, Webpack build and password/material/orders tests; new `tests/buyer-actions.test.mjs` checks valid intents and malicious return destinations. Browser script `/tmp/scrapmart-marketplace-correction-check.mjs` checks responsive layout, sidebar, drawer, home, counts, filters/sort/search, public detail links, action/login behavior, upload priority and Vendor regression. Review screenshots are under `/tmp/scrapmart-marketplace-correction-*`. Local preview: `http://localhost:3114`.

Backend, backend/docs, designer reference, Nigerian images/credits, generated assets and listing records remain untouched. No installations, commits, pushes or deployments.

Validation results: lint, TypeScript no-emit, Webpack build and four test files passed. Browser checks passed at 320, 390, 768, 1024 and 1440 pixels for marketplace, detail and Vendor dashboard. Six-result count, copper search, category filtering, ascending price order, Home navigation, drawer focus/Escape restoration, public View item, both action-to-login links, malicious return rejection, demo-login non-authentication and upload override/eligibility all passed. No runtime exceptions, failed images or API mutations. Desktop marketplace and mobile drawer screenshots visually inspected. Redirect tests additionally reject trailing newline characters.

Screenshots:
- /tmp/scrapmart-marketplace-correction-marketplace-desktop.png
- /tmp/scrapmart-marketplace-correction-marketplace-mobile.png
- /tmp/scrapmart-marketplace-correction-mobile-menu.png
- /tmp/scrapmart-marketplace-correction-detail-desktop.png
- /tmp/scrapmart-marketplace-correction-detail-mobile.png
