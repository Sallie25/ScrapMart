# Phase 2 marketplace validation — November 16, 2026

Workspace: `scrapmart-nov2/frontend`; branch: `feature/nov2-functional-integration`.
Starting checkpoint: `7db8dd2`. Initial tracked/untracked status was clean.

## Capability assessment

| Capability | Result | Evidence |
| --- | --- | --- |
| Vendor session and private shop information | PASS | Disposable Vendor login and onboarding GET returned 200; live capability and profile both report `pending`. Location/address fields are present. |
| Vendor listing creation and inventory management | BLOCKED | Own-listings GET and a valid disposable draft POST returned 403/`selling_forbidden`. No draft was created. |
| Product photo upload | BLOCKED | No authorized owned listing exists to upload against. Frontend/BFF now enforce the backend 3 MB JPEG/PNG contract; synthetic boundary and consent tests pass. No private ID was fabricated or submitted. |
| Publication | BLOCKED | Available Vendor is pending. No publish attempt was made. The backend requires approved evidence before listing operations. |
| Real categories and listing search | PASS | Public categories GET returned nine real categories; listings GET returned an empty page with no next cursor. The catalogue remains genuinely empty. |
| Live item details/photos and inline Vendor information | BLOCKED | Implemented against public listing DTOs, but zero published listings are available for a live item demonstration. Public DTOs expose business name and the consented listing location, never private shop address. |
| Standalone public Vendor profile | BLOCKED | The current API does not provide this resource; the existing UI explains that it is unavailable. |
| Order/message histories | PASS | Authenticated Buyer and Vendor history endpoints returned 200 with zero orders/conversations. These are real empty states. |
| Buyer contacts Vendor / Vendor receives message | BLOCKED | The conversation requires a real accessible listing. No available published listing; no message exchange was claimed or simulated as live. |
| Buyer places order / Vendor sees matching status | BLOCKED | No purchasable published listing exists. No real order, reservation, delivery, completion, or payment was created. |
| Permission enforcement | PASS | Buyer access to Vendor listing management returned 403. Backend approval controls were preserved. |
| Explicit sample fallback | PASS | `/demo/marketplace` uses existing presentation fixtures, separately from the live catalogue. Contact/order actions explicitly report that nothing real was created or sent. |

## Approval and infrastructure requirements

The backend's approved-evidence check requires:

1. An active Vendor with complete shop information.
2. A securely stored submitted government-ID image, plus the current evidence digest.
3. Verified ownership of the account's current phone number.
4. An authorized reviewer approval audit matching that exact current evidence.

Listing publication additionally requires complete item fields, valid approximate
coordinates, public-location consent, and stored sanitized product photos with
valid HTTPS delivery URLs. There is no separate listing-moderator approval step in
the inspected publication method; Vendor approval and listing completeness gate it.
Private ID storage and public product-photo storage must remain separate. Product
photos require a configured durable adapter with put/exists/public_url/delete.

The confirmed staging blocker is **pending Vendor approval**. Live SMS delivery,
private ID storage, review readiness, and public photo-storage configuration were
not independently established. Empty public listings and a healthy database cannot
prove those services are ready. No credentials, schemas, approval flags, provider
configuration, or backend files were changed, and no approval or phone proof was
bypassed. A synthetic ID was not uploaded. Previously observed phone-code 503s are
not enough to diagnose a particular missing provider in this phase.

## Frontend corrections

- Corrected JSX decimal patterns, which previously contained double backslashes,
  so prices accept two decimal places and quantities three, including Buyer order
  quantity inputs. The existing backend remains authoritative.
- Aligned product-photo/private-document UI limits and the binary BFF limit with
  the backend's 3 MiB maximum instead of advertising 5 MB uploads.
- Added a verification-information link to the blocked Vendor inventory state.
- Reused the approved sample images, listing-detail layout, and prototype contact
  form at `/demo/marketplace`, with prominent sample-only labels. Sample search
  and detail links stay separate from `/marketplace` and its real inventory.
- Clarified the sample contact/order feedback: no message, order, reservation, or
  payment is created. The direct Buyer-to-Vendor pay-on-delivery model is unchanged.

## Validation

25 focused marketplace/Vendor tests passed with zero failures/skips. These cover
catalogue contracts, filtering/pagination, location privacy, no silent fixture
fallback, approved route forwarding, permission failures, upload size boundaries,
and explicit image consent. All upstream transports in those tests are synthetic.

```sh
node --import ./tests/helpers/buyer-auth-loader.mjs \
  --import ./tests/helpers/session-loader.mjs \
  --import ./tests/helpers/marketplace-loader.mjs \
  --test --test-isolation=none tests/vendor-integration.test.mjs \
  tests/marketplace.test.mjs tests/marketplace-detail.test.mjs tests/marketplace-page.test.mjs
```

ESLint and `npm run build -- --webpack` passed, including TypeScript.

Real Edge against the local production build passed sample search, gallery/photo
loading, details, explicit no-op contact/order feedback, duplicate-query handling,
390/1440-pixel overflow checks, zero real mutations and zero runtime exceptions.
The first image assertion was premature for lazy-loaded images; waiting for those
images resolved it without an application change.

Real Edge on the deployed Preview passed the same sample journey before alias
assignment. After assignment, real Edge on the staging alias passed Vendor login,
pending profile, backend selling restriction, rendered decimal precision checks,
Vendor and Buyer genuine empty order/message histories, nine real categories,
live search and category navigation, and the labeled fallback. Vendor access to
Buyer-only orders was denied with 401; the assertion was corrected to accept the
backend's valid 401 or 403 denial, with no application change. The completed run
had zero browser exceptions and no sample-generated account/Vendor mutations.

Staging Preview: https://scrapmart-loc32xozw-pandas-neca.vercel.app

Deployment: `dpl_8JPR9gDaGfGhgi7vTEWTB8gZWmqA`, READY, Preview target.

Stable staging alias: https://scrapmart-bff-staging-pandas-neca.vercel.app

The alias was confirmed to reference this Preview after the candidate browser
checks passed. Previous staging deployment retained:
`dpl_EWR8Xa6LnceVoASW2BGxXiN9kXAB`. Only one Preview deployment was created for
this phase. Production, credentials, database schemas, Render configuration and
the approved November 2 design were unchanged. No push or merge was performed.

## Exact stakeholder demonstration

1. Open the staging Vendor login and sign in with the authorized disposable
   Vendor. Open `/vendor/dashboard?view=profile`; show **pending** and the genuine
   shop information. Explain that ID/phone evidence and authorized review are
   prerequisites. Do not upload fake ID, invent OTPs, or claim approval.
2. Open `/vendor/listings`; show the actual backend selling restriction and its
   verification link. Explain that no draft or publication was permitted.
3. Open `/marketplace`; browse the nine real categories and search/filter. State
   that there are currently no published items, rather than presenting fixtures
   as live inventory.
4. Announce the switch to **sample-data fallback**, then open
   `/demo/marketplace`. Search “Copper”, open the Copper Wire Bundle, and show its
   sample photo, description, quantity, price, location, and sample Vendor.
5. Use the sample Contact/Order controls. Read their explicit no-message/no-order
   confirmations. Explain the intended real flow and direct pay-on-delivery
   settlement. Do not describe this as a successful live Buyer–Vendor trade.

To unlock a live end-to-end trade, an authorized operator must complete genuine
Vendor evidence/review and confirm the separate storage/SMS services, then an
approved Vendor must upload a real product photo and publish a complete consented
listing. Buyer contact/order creation and matching Vendor receipt/status can only
be live-validated after that prerequisite exists.
