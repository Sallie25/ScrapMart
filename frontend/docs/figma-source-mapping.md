# Approved source mapping — 2026-11-02

Source: `/home/sallieakpan/Desktop/scrapmart-figma-reference/figma-make-reference/src/App.tsx`, `src/index.css`, and `README-REFERENCE.txt`. All readable. App.tsx defines the approved version; PNG names/order do not establish versions.

## Landing component mapping

| Reference          | Next.js target    | Details                                                                                                                              |
| ------------------ | ----------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Welcome            | /                 | Pay-on-delivery strip, sticky logo/account header, hero, demo metrics                                                                |
| HeroMediaSlider    | landing component | Four images in source order, 2500ms interval, 700ms fade, hover pause, dot controls, payment card                                    |
| OnboardingSections | landing component | Six SVG material tiles; buyer/seller tabs with three steps; three trust cards; five FAQs, first initially open; final dark-green CTA |
| OnboardingFooter   | landing component | Six areas: brand/social, buyers, vendors, support, legal, contact                                                                    |

Source fonts: DM Sans 400–800 and Manrope 600–800. Brand #08783e, dark #064829, light #74d99b, soft #e8f7ee, ink #14211a, muted #627067, canvas #f5f7f5, border #dfe6e1. Rounded cards, subtle shadows, max-w-7xl. Isolate landing styles from existing global tokens.

Hero assets (all source URLs use crop=entropy&cs=tinysrgb&fit=crop&fm=jpg&q=85&w=1200):

| Source image key | Unsplash photo                   | Local target                         | Source label     |
| ---------------- | -------------------------------- | ------------------------------------ | ---------------- |
| nigeriaJunkyard  | photo-1554146347-dc1eb254a96d    | /images/landing/vehicle-scrap.jpg    | Vehicle scrap    |
| nigeriaCart      | photo-1658402834638-c6f65944b551 | /images/landing/local-collection.jpg | Local collection |
| nigeriaVehicles  | photo-1573662766191-066ba9570a4b | /images/landing/auto-parts.jpg       | Auto parts       |
| nigeriaMarket    | photo-1673280401347-309363111070 | /images/landing/lagos-market.jpg     | Lagos market     |

No exported PNG is referenced anywhere in src/App.tsx or src/index.css. The material grid and logos use inline SVG, not PNGs. Do not substitute the existing Pexels/category photos for the four hero images.

FAQ: Is ScrapMart free?; How does pay on delivery work?; How are vendors verified?; What if the item isn't as described?; Which materials are not allowed?

## Screens and existing route destinations

| Reference screen/component    | Existing route                | Gap / behavior                                                                                                                |
| ----------------------------- | ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| welcome / Welcome             | /                             | Landing implementation scope                                                                                                  |
| role / RoleSelect             | /onboarding                   | Existing buy/sell intent and role selection                                                                                   |
| signup / Signup               | /signup?role=buyer or vendor  | Existing validated forms preserved; source adds password, consent and vendor ID upload                                        |
| login / Login                 | /login                        | Source role switching changes React state only; existing form does not authenticate                                           |
| Login recovery subview        | /forgot-password              | Existing honest demo; source falsely claims reset sent without network                                                        |
| otp / Otp                     | none                          | Only accepts hardcoded 123456; resend button has no handler; no real verification                                                                                                |
| verify / VendorVerify         | none                          | Immediately claims verified identity/phone/shop after demo OTP; no backend approval                                                                                  |
| home / BuyerHome              | none                          | Distinct buyer overview, metrics, categories, nearby listings                                                                 |
| search / SearchPage           | /marketplace                  | Preserve existing query/category/location/condition/price filtering and sorting                                               |
| product / ProductDetail       | /listings/[id]                | Source gallery, order/report actions; preserve working existing detail and local photo loading                                |
| vendor / VendorProfile        | /vendors/[slug]               | Source fixed sample vendor versus existing per-vendor route                                                                   |
| location / Location           | existing external map links   | Prototype map/satellite display; vendor update confirmation not persisted                                                     |
| messages / Messages           | none; contact form on listing | Source appends messages to component state; no delivery or persistence                                                        |
| order / OrderForm             | none                          | Quantity and summary; place action only app state; no transaction                                                             |
| orders / Orders               | none                          | Buyer tabs change appearance but do not filter source rows                                                                    |
| orderDetail / OrderDetail     | none                          | Six manual stages; source always opens latest order, not selected order                                                       |
| dashboard / VendorDashboard   | /vendor/dashboard             | Existing browser-local listings; source hardcoded verified vendor and completed sales                                         |
| listings / MyListings         | /vendor/dashboard (partial)   | Source tabs, pause/activate/sold/delete in app state; edit opens prefilled AddListing, no item editing                        |
| add / AddListing              | /vendor/listings/new          | Preserve existing upload validation, IndexedDB photo and localStorage metadata; source uses sample photo and hardcoded fields |
| bulk / BulkUpload             | none                          | Sample items; selected files are not parsed into listings                                                                     |
| vendorOrders / Orders         | none                          | Manual order status advance only                                                                                              |
| profile / Profile             | none                          | Fixed demo identity/contact/metrics                                                                                           |
| settings / Settings           | none                          | Toggles/password state and success toasts; no server writes; logout navigates welcome                                         |
| notifications / Notifications | none                          | Static role-specific examples                                                                                                 |

AppHeader: buyer sidebar links Overview, Browse Marketplace, My Orders, Messages. Vendor links Overview, My Listings, Add New Item, Customer Orders, Messages. Account links Profile and Settings; top bar notifications/profile; mobile overlay drawer with close controls. No authenticated account switching: Login switch changes role; registration offers buyer/vendor paths. App uses hash/history screen state; do not import its router into Next.js.

## Prototype limitations to preserve honestly

Statistics 1,200+/500+/10+, verification badges, 146 completed sales, contact number +234 801 234 5678, support email, OTP, notifications, order/payment progression, messaging and publish-success claims are demonstration content. Existing Next.js auth, recovery and contact forms explicitly disclose that no backend operation occurred. Keep those disclosures. Existing vendor listings/photos persist only in this browser; marketplace currently shows static demo listings only.

Footer source support/legal buttons route to login; socials other than WhatsApp use '#'. Do not present placeholder contact links as live support or invent legal pages.

## Small implementation batches

1. Landing only: exact source sections, four local hero assets, isolated typography/tokens, real route links, accessible tabs/FAQ/slideshow, clear demo metrics/contact/policy wording. No shared header changes.
2. Onboarding/auth visual adaptation: reuse existing validation and routes; do not simulate auth/OTP/verification success.
3. Buyer screens: adapt marketplace/detail/vendor visuals while retaining existing filters, data IDs, map links and photo behavior. Buyer dashboard requires its own scoped route.
4. Vendor screens: adapt dashboard/new-listing visuals; preserve local save/remove/photo consistency. Inventory editing, statuses and bulk upload require separate scope.
5. Orders/messages/account views: only after explicit demo/live contracts and route design; never port false operational success toasts.
6. Presentation review: desktop/mobile layout, keyboard controls, exact asset loading, existing route smoke checks, lint/type/build checks.

Shared conflict points: site-header.tsx; globals.css; layout.tsx; `components/ui/*`; `components/forms/*`; lib/validations/auth.ts; `components/marketplace/*`; `lib/data/*`; public/images; package.json/package-lock.json; next.config.ts. Landing work should use isolated files and preserve existing components. Backend PRD remains untracked and untouched.

## Exact external image URLs in the reference

The full source contains the following URLs. These remain external in the reference; only the four landing URLs are localized for production frontend use in this batch.

- https://images.unsplash.com/photo-1527383418406-f85a3b146499?crop=entropy&cs=tinysrgb&fit=crop&fm=jpg&q=85&w=1200
- https://images.unsplash.com/photo-1615906655593-ad0386982a0f?crop=entropy&cs=tinysrgb&fit=crop&fm=jpg&q=85&w=1200
- https://images.unsplash.com/photo-1429772011165-0c2e054367b8?crop=entropy&cs=tinysrgb&fit=crop&fm=jpg&q=85&w=1200
- https://images.unsplash.com/photo-1640602344715-a6ef5c281037?crop=entropy&cs=tinysrgb&fit=crop&fm=jpg&q=85&w=1200
- https://images.unsplash.com/photo-1687612177175-81f81bab519a?crop=entropy&cs=tinysrgb&fit=crop&fm=jpg&q=85&w=1200
- https://images.unsplash.com/photo-1619642751034-765dfdf7c58e?crop=entropy&cs=tinysrgb&fit=crop&fm=jpg&q=85&w=1200
- https://images.unsplash.com/photo-1624192647570-1131acc12ccf?crop=entropy&cs=tinysrgb&fit=crop&fm=jpg&q=85&w=1200
- https://images.unsplash.com/photo-1606053929013-311c13f97b5f?crop=entropy&cs=tinysrgb&fit=crop&fm=jpg&q=85&w=1200
- https://images.unsplash.com/photo-1554146347-dc1eb254a96d?crop=entropy&cs=tinysrgb&fit=crop&fm=jpg&q=85&w=1200
- https://images.unsplash.com/photo-1658402834638-c6f65944b551?crop=entropy&cs=tinysrgb&fit=crop&fm=jpg&q=85&w=1200
- https://images.unsplash.com/photo-1573662766191-066ba9570a4b?crop=entropy&cs=tinysrgb&fit=crop&fm=jpg&q=85&w=1200
- https://images.unsplash.com/photo-1673280401347-309363111070?crop=entropy&cs=tinysrgb&fit=crop&fm=jpg&q=85&w=1200
- https://images.unsplash.com/photo-1687612177175-81f81bab519a?crop=entropy&cs=tinysrgb&fit=crop&fm=jpg&q=80&w=400
- https://images.unsplash.com/photo-1722695510527-cc033e43be1b?crop=entropy&cs=tinysrgb&fit=crop&fm=jpg&q=80&w=400
- https://images.unsplash.com/photo-1638983851342-63e1aa939a7a?crop=entropy&cs=tinysrgb&fit=crop&fm=jpg&q=80&w=400
- https://images.unsplash.com/photo-1608224873587-81ee37394b4e?crop=entropy&cs=tinysrgb&fit=crop&fm=jpg&q=80&w=400
- https://images.unsplash.com/photo-1606337321936-02d1b1a4d5ef?crop=entropy&cs=tinysrgb&fit=crop&fm=jpg&q=80&w=400
- https://images.unsplash.com/photo-1642801069630-bbb4d78061be?crop=entropy&cs=tinysrgb&fit=crop&fm=jpg&q=80&w=400
- https://images.unsplash.com/photo-1613223968777-9a59c6f8c4de?crop=entropy&cs=tinysrgb&fit=crop&fm=jpg&q=80&w=400

## Implemented presentation batch

Landing now uses the four local hero JPEGs and exact source SVG paths. The source layout and colors are retained with scoped CSS variables; existing routes use Next.js links. Added manual slideshow pause, focus pause and reduced-motion handling. Mobile header links retain access to existing routes. Sample statistics/contact details and planned verification are explicitly labelled; unavailable support/legal actions point to disclosure text instead of pretending to perform operations.

Fonts are local variable WOFF2 assets in `src/app/fonts`, with original download URLs in `SOURCES.json` and SIL Open Font Licenses included. DM Sans and Manrope match the source typography. Existing Geist and Geist Mono are also self-hosted: `layout.tsx` only changes font loading, preserving the existing font CSS variable names. This shared-file change removes build-time Google Fonts network failures. No package manifest changes.

Environment validation note: default Turbopack build was blocked by worker-port permissions. Validate with `npm run build -- --webpack` in this environment; no build-script change is required.

## Reference image callsites

- `images.engine`, `engine2`, `wires`, `metal`, `parts`, `mechanic`, and `clothes` supply the seven initial sample listings. They are reused by product/category/inventory/bulk-upload views. `ProductDetail` also repeats the item image alongside `parts` and `mechanic` as sample thumbnails.
- `images.textiles` (`photo-1606053929013-311c13f97b5f`) is declared but unused.
- `nigeriaJunkyard`, `nigeriaCart`, `nigeriaVehicles`, and `nigeriaMarket` are used exclusively by `HeroMediaSlider`.
- The category array adds direct Unsplash URLs for Scrap Metal (a different size/quality variant of `images.metal`), Aluminium, Iron, Electronics, Machinery, Batteries and Plastics. Clothes, Copper, Car Parts and Other reuse named image keys.
- No remote image URL remains in the implemented landing component. The untouched reference still uses its external URLs.

## Validation

- `npm run lint`: passed.
- `npm run build -- --webpack`: passed, including TypeScript and all route generation. Default Turbopack is restricted by this environment's worker-port permissions.
- Browser checks: all four hero images decoded with cover crop; automatic rotation, pause, dot selection, buyer/seller views, FAQ expansion/collapse, six footer areas and mobile route navigation passed.
- No horizontal overflow at 320, 390, 768 and 1440 pixels. All twelve existing route variants checked returned HTTP 200; no browser runtime exceptions.
- Desktop/mobile screenshots are review artifacts in `/tmp/scrapmart-landing-desktop.png` and `/tmp/scrapmart-landing-mobile.png`.

Branch remains `feature/frontend-buyer-vendor-integration`. No commits, pushes or deployment. Backend and its untracked PRD are untouched.
