# Browser authentication checkpoint — November 16, 2026

Workspace: `scrapmart-nov2/frontend`, branch `feature/nov2-functional-integration`.
Existing tracked and untracked authentication changes were preserved and completed.

## Cause and resulting behavior

The login UI needed a session-resolution state before accepting credentials.
`session_refresh_required` means expired access with a browser session still present;
it cannot be treated as anonymous. The BFF deliberately rejects login while a
browser identifier remains, using `logout_required`. Temporary session lookup
failures likewise must not enable login. Tests cover these distinct responses.

The interrupted form/client work now blocks submission until anonymous status is
confirmed, performs one CSRF-protected refresh and recheck for expired access,
keeps outages recoverable, discovers the dashboard from live capabilities, and
requires confirmed logout plus an anonymous recheck before account switching.
Overlapping resolution calls share their promise, preventing duplicate refresh
spending when React replays a mount effect. Confirmed-logout feedback is consumed
only after the anonymous session is established. Logout Retry handling and the
earlier empty-POST-stream transport fix remain intact.

Registration displays “Registration request received!”, “You can now try logging
in to ScrapMart.” and a role-specific Log in link. Accepted requests clear the
password. The backend acknowledgment and duplicate protections remain unchanged.

## Validation

- ESLint passed.
- `npm run build -- --webpack` passed, including TypeScript.
- 142 offline tests passed with zero failures or skips:

  ```sh
  node --import ./tests/helpers/buyer-auth-loader.mjs \
    --import ./tests/helpers/session-loader.mjs \
    --import ./tests/helpers/marketplace-loader.mjs \
    --test --test-isolation=none tests/*.test.mjs
  ```

- Real headless Edge 157 against the local production build, using mocked BFF
  responses: initial checking blocks login; both role forms detect existing
  sessions; failed logout keeps login blocked; confirmed account switching enables
  login; expired access refreshes once; invalid refresh permits login only after
  recheck; service outage exposes Retry; registration clears passwords and links
  to the correct role. Zero browser runtime exceptions.
- Real Edge against the live staging alias: both roles completed registration
  acknowledgment → login → dashboard → confirmed logout → login again. Existing
  session detection from the other role's login page, Go to dashboard, and account
  switching passed. Zero browser runtime exceptions. Existing demo accounts were
  used; registration checks exercised the privacy-safe acknowledgment without
  asserting fresh account creation. Expiry/outage behavior was mocked, not induced
  against live infrastructure.
- Preview Buyer/Vendor login and signup pages returned 200; anonymous session
  returned 401/session_required. Direct Preview auth mutations returned the
  expected 403/origin_or_csrf_rejected because the BFF pins the stable staging
  origin. No origin controls were relaxed. Live mutations were verified only
  after assigning the validated Preview to the stable staging alias.

Browser automation used Edge's existing DevTools protocol and Node's built-in
WebSocket; no browser dependencies were installed. Protected requests used an
in-memory development OIDC token, scoped to the staging origin. No authentication
state, tokens, passwords, or screenshots were added to the repository.

## Intermittent 503 investigation

The historical auth 503 cause remains unverified. Backend database readiness
returned 200 in approximately 0.8 seconds and both current live auth journeys
passed. Vercel request metadata for the checked 30-minute window showed one 503
on `/api/vendor/phone/send-code`, not an authentication route. This does not
establish the earlier auth failure's cause. The runtime-log connector returned
400 Bad Request due to retention and was not retried. Render had no selected
workspace, so its logs were not queried. No timeout, connectivity, database,
credential, or infrastructure configuration changes were made speculatively.

## Staging release

Preview: https://scrapmart-aw5f1e3m8-pandas-neca.vercel.app

Deployment: `dpl_EWR8Xa6LnceVoASW2BGxXiN9kXAB`, READY, Preview target.

Stable alias: https://scrapmart-bff-staging-pandas-neca.vercel.app

Alias assignment was verified after the candidate build, local tests, browser
mock checks, and candidate reads passed. Both live role journeys then passed.
Previous staging deployment retained: `dpl_CbdixarVQCjD8mvA826KZqtrKWAW`.

Production, credentials, Neon schemas, Render configuration, and the approved
November 2 design were unchanged. The local checkpoint includes only the reviewed
authentication work, its tests, and this validation record; no push or merge.
