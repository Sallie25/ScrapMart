# Batch A — authentication and onboarding review

Starting branch: `feature/frontend-buyer-vendor-integration`.
Starting commit: `d343c74d271f90e26f03e5dffe43ff597923bbef`.

## Source and scope

Read the approved local `App.tsx` components AuthShell, RoleSelect, Signup, Login (including recovery), Otp and VendorVerify, plus `index.css`. The implementation retains the source fonts, palette, card layout, dark sidebars, field arrangement and responsive breakpoints. Existing Input, Label and Button primitives and React Hook Form/Zod validation are reused. Auth CSS and local font variables are scoped to `.sm-auth`.

Implemented existing routes: `/onboarding`, `/signup?role=buyer`, `/signup?role=vendor`, `/login` (with optional role query), `/forgot-password` (with optional role query).

No landing components, landing assets, global styles, root layout, shared header, package manifests, backend files or reference source were changed. The backend PRD remains untracked and untouched.

## Interactions

- Buyer/vendor role cards link to the corresponding signup or existing-account login route.
- Onboarding buy/sell intent highlighting and signup back links are preserved.
- Login supports Buyer/Vendor role switching through query parameters. This selects a UI journey, not an authenticated account switch.
- Signup validates name, email, contact phone, backend-compatible signup password rules and acknowledgement of demo behavior. Vendor preview additionally validates business name, city/location and address. Existing name, email, phone, business-name and address validation was retained.
- Login accepts email rather than the reference's phone-or-email field. Password visibility remains interactive.
- Recovery validates email and preserves role on return to login.
- Signup preview clears the password after validation. No form sends or persists credentials or registration data.
- Vendor ID type/upload controls are visibly disabled, with a clear explanation. No identity document can be submitted or stored.

## Deliberate differences and integration prerequisite

The authoritative backend is `/home/sallieakpan/Desktop/scrapmart-backend/backend`, branch `feature/database-models`, verified HEAD `f446f2f46de0040ebffd2df0e2870841d9468b1c`. The legacy backend inside the frontend repository must not be used for API contracts.

Read-only inspection of `app/modules/auth/security.py`, `registration_schemas.py`, `login_schemas.py`, `vendor_schemas.py`, `app/modules/vendors/onboarding_schemas.py`, and relevant `app/api/v1/` routes confirms:

- Signup passwords: 15–128 Unicode code points, valid strict UTF-8 text, no null characters, not all Python whitespace. Unicode/spaces are allowed; passwords are never trimmed, normalized or truncated. No composition requirements.
- Login passwords: separate 1–128-code-point boundary, valid UTF-8, no nulls. Short and all-whitespace existing credentials are not rejected by signup-only rules.
- Frontend validation counts code points rather than UTF-16 code units and rejects lone surrogates; signup whitespace handling matches Python `str.isspace()`, including U+001C–001F and U+0085, excluding U+FEFF.
- `POST /api/v1/auth/buyer/signup`: strict JSON `email`, `password`, `full_name` (1–150), optional `phone_number` (up to 20); provided text must be nonblank, UTF-8 encodable and null-free.
- `POST /api/v1/auth/vendor/signup`: same payload plus `business_name` (1–200, nonblank, null-free, UTF-8). Extra fields are forbidden.
- Both signup endpoints return HTTP 202 with the generic acknowledgment `If registration was successful, you can now sign in.` This is not proof of account creation or vendor approval.
- Signup/login require an allowed Origin, `X-ScrapMart-CSRF: 1`, JSON content type and rate-limit admission. Validation errors are 422 with safe field names; credentials must never appear in errors. Requests may return 403/415/429/503 as applicable.
- Login uses role-specific buyer/vendor endpoints with `email` and `password`, not a phone login identifier. Login returns a bearer access token plus refresh-session cookie handling; no session is created by this UI preview.
- Shop location/address are a separate private onboarding contract. Do not send `businessLocation`, `businessAddress`, `previewConsent`, or camelCase form keys directly to strict registration endpoints. Payload mapping and actual integration are deliberately deferred; the existing UI's name/phone/business rules are not a complete mirror of backend field limits or email canonicalization.

All future integration batches must inspect the relevant actual backend schemas, endpoints, permissions and Origin/CSRF/session requirements first. Backend reference remains read-only. The user-provided staging API is `https://scrapmart-api-staging.onrender.com`; no staging requests were made for this checkpoint.

No OTP delivery or OTP acceptance flow is simulated. The reference's hardcoded `123456`, immediate VendorVerify success, login redirect and reset-sent success are deliberately not copied. Preview completion explicitly says no account/session/recovery request was created or sent. Vendor approval remains required and is never automatically granted. Actual Terms/Privacy pages do not exist, so the checkbox acknowledges demo behavior instead of purporting to record legal consent.

## Validation

- `npm run lint`: passed.
- `npm run build -- --webpack`: passed, including TypeScript and route generation.
- Browser: landing still renders its four-image hero and role CTAs.
- Browser: buyer/vendor onboarding links; empty and invalid email signup errors; demo acknowledgement; valid registration preview without account/approval claims; password cleared after preview; disabled government-ID controls.
- Browser: phone identifier rejected for email login; show/hide password; role switch/recovery/back links; no authentication or recovery-delivery claims.
- All six view variants checked at 320, 390, 768 and 1440 pixels without horizontal overflow.
- No browser runtime exceptions. No POST/mutation requests from demo forms.

Screenshots are in `/tmp/`, named `scrapmart-auth-{view}-{desktop|mobile}.png`, where view is `onboarding`, `signup-buyer`, `signup-vendor`, `login-buyer`, `login-vendor`, or `recovery`.

Ready for visual review and a separately scoped Buyer dashboard UI batch. Live authentication still requires explicit payload mapping and session/CSRF integration; no such services are claimed by these demo screens. No pushes or deployments were made. This local checkpoint contains only Batch A frontend work; the backend reference remains read-only.

## Final security checkpoint checks

`node --test tests/auth-passwords.test.mjs` checks both signup schemas and the independent login boundary: minimum/maximum length, astral Unicode code-point counting, preserved boundary spaces, combining characters, Python whitespace differences, null characters and lone surrogate rejection. Runtime/browser validation remains demo-only.

Final security correction: four regression tests passed, and 47 vectors evaluated with the actual backend signup/login validation functions matched all three frontend password schemas. Browser checks also confirmed rejection of short, overlong and all-whitespace signup passwords for both roles, with password visibility and demo submission preserved.
