import 'server-only';
import { z } from 'zod';
import { BackendAuthClient, BackendFailure, boundedJson, exactHttpsOrigin } from './backend';
import { buyerRegistration, vendorRegistration, vendorEnrollment, vendorOnboardingPatch, login, acknowledgment, safeFields } from './contracts';
import type { Role } from './contracts';
import { hashIdentifier } from '../sessions/crypto';
import { browserSessionCookie } from '../sessions/index';
import type { SessionStore } from '../sessions/store';
import { SessionAccessExpired } from '../sessions/store';

const headers = { 'Cache-Control': 'no-store', 'Vary': 'Cookie', 'X-Content-Type-Options': 'nosniff' };
function response(body: unknown, status = 200): Response {
  return status === 204 ? new Response(null, { status, headers }) : Response.json(body, { status, headers });
}
export function authError(status: number, code: string, fields: string[] = []): Response {
  return response({ detail: { code, message: 'Authentication request could not be completed.',
    fields: fields.filter(field => safeFields.includes(field)) } }, status);
}
function backendError(error: unknown): Response {
  if (!(error instanceof BackendFailure)) return authError(503, 'session_unavailable');
  const codes: Record<number, string> = { 400: 'invalid_session_cookie', 401: 'invalid_credentials',
    403: 'forbidden', 409: 'case_changed', 413: 'request_too_large', 415: 'json_required', 422: 'validation_error',
    429: 'rate_limited', 502: 'backend_invalid_response', 503: 'backend_unavailable' };
  const result = authError(error.status, codes[error.status] ?? 'backend_unavailable', error.fields);
  if (error.status === 429 && error.retryAfter) result.headers.set('Retry-After', error.retryAfter);
  return result;
}
function cookie(response: Response, identifier?: string, expiry?: Date): Response {
  const value = identifier ?? '';
  const expires = expiry ?? new Date(0);
  const age = identifier ? Math.max(0, Math.floor((expires.getTime() - Date.now()) / 1000)) : 0;
  response.headers.set('Set-Cookie', `${browserSessionCookie.name}=${value}; Path=/; Expires=${expires.toUTCString()}; Max-Age=${age}; Secure; HttpOnly; SameSite=Lax`);
  return response;
}
function identifier(request: Request): string | undefined {
  const matching = (request.headers.get('cookie') ?? '').split(';').map(part => part.trim())
    .filter(part => part.split('=', 1)[0] === browserSessionCookie.name);
  if (matching.length === 0) return undefined;
  if (matching.length !== 1) throw new BackendFailure(400);
  const value = matching[0].slice(matching[0].indexOf('=') + 1);
  try { hashIdentifier(value); } catch { throw new BackendFailure(400); }
  return value;
}

export function createBffHandlers(dependencies?: { store: SessionStore; backend: BackendAuthClient; browserOrigin: string }) {
  const origin = dependencies ? exactHttpsOrigin(dependencies.browserOrigin) : undefined;
  return async function handle(request: Request, operation: readonly string[]): Promise<Response> {
    const path = operation.join('/');
    const registration = path === 'buyer/signup' || path === 'vendor/signup';
    const signingIn = path === 'buyer/login' || path === 'vendor/login';
    const enrolling = path === 'vendor/enroll';
    const onboarding = path === 'vendor/onboarding';
    const identityUpload = path === 'vendor/identity-document';
    const phoneSend = path === 'phone/send-code';
    const phoneVerify = path === 'phone/verify-code';
    const reviewSubmission = path === 'vendor/verification/submit';
    const reviewQueue = path === 'verification/cases';
    const reviewDetail = operation.length === 3 && operation[0] === 'verification' && operation[1] === 'cases' && /^[0-9a-fA-F-]{36}$/.test(operation[2]);
    const reviewerRead = reviewQueue || reviewDetail;
    const reviewerDecision = operation.length === 4 && operation[0] === 'verification' &&
      operation[1] === 'cases' && /^[0-9a-fA-F-]{36}$/.test(operation[2]) &&
      (operation[3] === 'approve' || operation[3] === 'reject');
    const read = path === 'session' || path === 'vendor/status';
    if (!registration && !signingIn && !enrolling && !onboarding && !identityUpload && !phoneSend && !phoneVerify && !reviewSubmission && !reviewerRead && !reviewerDecision && !read && path !== 'refresh' && path !== 'logout') return authError(404, 'not_found');
    if (onboarding ? !['GET', 'PATCH'].includes(request.method) : request.method !== (read || reviewerRead ? 'GET' : 'POST')) return authError(405, 'method_not_allowed');
    if (!dependencies || !origin) return authError(503, 'authentication_disabled');
    const { store, backend } = dependencies;
    if (!read && !reviewerRead && !(onboarding && request.method === 'GET') && (request.headers.get('origin') !== origin || new URL(request.url).origin !== origin ||
        request.headers.get('x-scrapmart-csrf') !== '1' ||
        (request.headers.has('sec-fetch-site') && request.headers.get('sec-fetch-site') !== 'same-origin'))) {
      return authError(403, 'origin_or_csrf_rejected');
    }
    try {
      if (!read && !registration && !signingIn && !enrolling && !onboarding && !identityUpload && !phoneSend && !phoneVerify && !reviewSubmission && !reviewerRead && !reviewerDecision && request.body) {
        void request.body.cancel().catch(() => {});
        return authError(400, 'body_not_allowed');
      }
      if (registration || signingIn) {
        if (request.headers.get('content-type')?.split(';', 1)[0].trim().toLowerCase() !== 'application/json') return authError(415, 'json_required');
        const role = operation[0] as Role;
        const input = await boundedJson(request.body, AbortSignal.any([request.signal, AbortSignal.timeout(5000)]));
        const parsed = (signingIn ? login : role === 'buyer' ? buyerRegistration : vendorRegistration).safeParse(input);
        if (!parsed.success) return authError(422, 'validation_error', parsed.error.issues
          .map(issue => String(issue.path[0])).filter(field => safeFields.includes(field)));
        if (registration) { await backend.register(role, parsed.data); return response({ message: acknowledgment }, 202); }
        // Account switching must explicitly log out first; never replace a known
        // browser identifier while its local family might still be authorized.
        if (identifier(request)) return authError(409, 'logout_required');
        const authenticated = await backend.login(role, parsed.data);
        try {
          const id = await store.create(authenticated.credentials, authenticated.expiresAt);
          return cookie(response({ authenticated: true }), id, authenticated.expiresAt);
        } catch {
          try { await backend.logout(authenticated.credentials.refreshCookie); } catch { /* Unconfirmed orphan: never report login success. */ }
          return authError(503, 'session_unavailable');
        }
      }
      const id = identifier(request);
      if (path === 'logout') {
        if (!id) return cookie(response(null, 204));
        let backendConfirmed = false;
        // Use the validated single-use refresh claim as a logout fence. The
        // callback performs only backend logout and ALWAYS throws, so refresh
        // completion/rotation cannot run. No credential accessor is added.
        try {
          await store.refresh(id, async refreshCookie => {
            await backend.logout(refreshCookie); backendConfirmed = true;
            throw new Error('Terminal logout: no replacement credentials');
          });
        } catch { /* Expected terminal callback, or unconfirmed backend/claim failure. */ }
        let localConfirmed = false;
        try { await store.revoke(id); localConfirmed = true; } catch { /* Storage errors never become successful logout. */ }
        return cookie(backendConfirmed && localConfirmed ? response(null, 204) : authError(503, 'logout_unconfirmed'));
      }
      if (!id) return cookie(authError(401, 'session_required'));
      const metadata = await store.lookup(id); // Any storage error propagates as 503.
      if (!metadata) return cookie(authError(401, 'session_required'));
      if (reviewerDecision) {
        if ([...new URL(request.url).searchParams.keys()].length) return authError(422, 'validation_error');
        if (request.headers.get('content-type')?.split(';', 1)[0].trim().toLowerCase() !== 'application/json')
          return authError(415, 'json_required');
        const input = await boundedJson(request.body, AbortSignal.any([request.signal, AbortSignal.timeout(5000)]));
        const parsed = z.object({
          expected_version: z.number().int().min(0).max(Number.MAX_SAFE_INTEGER),
          expected_evidence_revision: z.string().min(1).max(256),
          reason: z.string().min(1).max(500).refine(value => value.trim().length > 0 && !/[\\u0000-\\u001f\\u007f]/.test(value)),
        }).strict().safeParse(input);
        if (!parsed.success) return authError(422, 'validation_error');
        try {
          return await store.withAccess(id, async access => {
            await backend.decideVerificationCase(access, operation[2],
              operation[3] as 'approve' | 'reject', parsed.data);
            return response({ decision_recorded: true });
          });
        } catch (error) {
          if (error instanceof SessionAccessExpired) return authError(401, 'session_refresh_required');
          if (error instanceof BackendFailure && error.status === 401) return authError(401, 'session_refresh_required');
          return backendError(error);
        }
      }
      if (reviewerRead) {
        let status: 'pending' | 'approved' | 'rejected' | 'suspended' = 'pending';
        let limit = 25;
        const params = new URL(request.url).searchParams;
        if (reviewQueue) {
          if ([...params.keys()].some(key => key !== 'status' && key !== 'limit') ||
              params.getAll('status').length > 1 || params.getAll('limit').length > 1)
            return authError(422, 'validation_error');
          const suppliedStatus = params.get('status') ?? 'pending';
          if (!['pending', 'approved', 'rejected', 'suspended'].includes(suppliedStatus))
            return authError(422, 'validation_error');
          status = suppliedStatus as typeof status;
          if (params.has('limit')) {
            const input = params.get('limit') ?? '';
            if (!/^[1-9][0-9]?$/.test(input) || Number(input) > 25) return authError(422, 'validation_error');
            limit = Number(input);
          }
        } else if ([...params.keys()].length) return authError(422, 'validation_error');
        try {
          return await store.withAccess(id, async access => response(
            reviewQueue ? await backend.reviewCases(access, status, limit) :
              await backend.reviewCase(access, operation[2])
          ));
        } catch (error) {
          if (error instanceof SessionAccessExpired) return authError(401, 'session_refresh_required');
          if (error instanceof BackendFailure && error.status === 401) return authError(401, 'session_refresh_required');
          return backendError(error);
        }
      }
      if (reviewSubmission) {
        if (request.headers.get('content-type')?.split(';', 1)[0].trim().toLowerCase() !== 'application/json')
          return authError(415, 'json_required');
        const input = await boundedJson(request.body, AbortSignal.any([request.signal, AbortSignal.timeout(5000)]));
        if (!z.object({}).strict().safeParse(input).success) return authError(422, 'validation_error');
        try {
          return await store.withAccess(id, async access => {
            await backend.submitVendorVerification(access);
            return response({ submitted_for_review: true });
          });
        } catch (error) {
          if (error instanceof SessionAccessExpired) return authError(401, 'session_refresh_required');
          if (error instanceof BackendFailure && error.status === 401) return authError(401, 'session_refresh_required');
          return backendError(error);
        }
      }
      if (phoneSend || phoneVerify) {
        if (request.headers.get('content-type')?.split(';', 1)[0].trim().toLowerCase() !== 'application/json')
          return authError(415, 'json_required');
        const input = await boundedJson(request.body, AbortSignal.any([request.signal, AbortSignal.timeout(5000)]));
        let verifiedCode: string | undefined;
        if (phoneSend) {
          if (!z.object({}).strict().safeParse(input).success) return authError(422, 'validation_error');
        } else {
          const parsed = z.object({ code: z.string().regex(/^[0-9]{6}$/) }).strict().safeParse(input);
          if (!parsed.success) return authError(422, 'validation_error');
          verifiedCode = parsed.data.code;
        }
        try {
          return await store.withAccess(id, async access => {
            if (phoneSend) {
              await backend.sendPhoneVerificationCode(access);
              return response({ message: 'If a code can be sent, delivery will be attempted.' }, 202);
            }
            await backend.verifyPhoneCode(access, verifiedCode!);
            return response(null, 204);
          });
        } catch (error) {
          if (error instanceof SessionAccessExpired) return authError(401, 'session_refresh_required');
          if (error instanceof BackendFailure && error.status === 401) return authError(401, 'session_refresh_required');
          if (error instanceof BackendFailure && error.status === 400) return authError(400, 'invalid_code');
          return backendError(error);
        }
      }
      if (identityUpload) {
        const identificationType = new URL(request.url).searchParams;
        const keys = [...identificationType.keys()];
        if (keys.length !== 1 || keys[0] !== 'identification_type') return authError(422, 'validation_error');
        const kind = identificationType.get('identification_type') ?? '';
        if (!['national_id', 'passport', 'drivers_license', 'voter_id'].includes(kind))
          return authError(422, 'validation_error');
        const mediaType = request.headers.get('content-type')?.trim().toLowerCase() ?? '';
        if (!['image/jpeg', 'image/png'].includes(mediaType)) return authError(415, 'unsupported_media_type');
        const maxBytes = 3 * 1024 * 1024;
        const claimedLength = request.headers.get('content-length');
        if (claimedLength !== null && (!/^\\d+$/.test(claimedLength) || Number(claimedLength) > maxBytes))
          return authError(413, 'request_too_large');
        if (!request.body) return authError(422, 'validation_error');
        const reader = request.body.getReader();
        const parts: Uint8Array[] = [];
        let count = 0;
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            count += value.byteLength;
            if (count > maxBytes) { void reader.cancel().catch(() => {}); return authError(413, 'request_too_large'); }
            parts.push(value);
          }
        } catch { return authError(422, 'validation_error'); }
        finally { reader.releaseLock(); }
        if (count === 0) return authError(422, 'validation_error');
        const bytes = new Uint8Array(count);
        let offset = 0;
        for (const part of parts) { bytes.set(part, offset); offset += part.byteLength; }
        try {
          return await store.withAccess(id, async access => {
            await backend.uploadIdentityDocument(access, kind, bytes, mediaType);
            return response({ submitted: true });
          });
        } catch (error) {
          if (error instanceof SessionAccessExpired) return authError(401, 'session_refresh_required');
          if (error instanceof BackendFailure && error.status === 401) return authError(401, 'session_refresh_required');
          return backendError(error);
        }
      }
      if (onboarding) {
        let patch: { business_name?: string; shop_location?: string; shop_address?: string } | null = null;
        if (request.method === 'PATCH') {
          if (request.headers.get('content-type')?.split(';', 1)[0].trim().toLowerCase() !== 'application/json')
            return authError(415, 'json_required');
          const input = await boundedJson(request.body, AbortSignal.any([request.signal, AbortSignal.timeout(5000)]));
          const parsed = vendorOnboardingPatch.safeParse(input);
          if (!parsed.success) return authError(422, 'validation_error');
          patch = parsed.data;
        }
        try {
          return await store.withAccess(id, async access => response(
            patch ? await backend.updateVendorOnboarding(access, patch) : await backend.getVendorOnboarding(access)
          ));
        } catch (error) {
          if (error instanceof SessionAccessExpired) return authError(401, 'session_refresh_required');
          if (error instanceof BackendFailure && error.status === 401) return authError(401, 'session_refresh_required');
          return backendError(error);
        }
      }
      if (enrolling) {
        if (request.headers.get('content-type')?.split(';', 1)[0].trim().toLowerCase() !== 'application/json')
          return authError(415, 'json_required');
        const input = await boundedJson(request.body, AbortSignal.any([request.signal, AbortSignal.timeout(5000)]));
        const parsed = vendorEnrollment.safeParse(input);
        if (!parsed.success) return authError(422, 'validation_error', parsed.error.issues
          .map(issue => String(issue.path[0])).filter(field => safeFields.includes(field) || field === 'current_password'));
        try {
          return await store.withAccess(id, async access => {
            await backend.enrollVendor(access, parsed.data);
            return response(null, 204);
          });
        } catch (error) {
          if (error instanceof SessionAccessExpired) return authError(401, 'session_refresh_required');
          if (error instanceof BackendFailure && error.status === 401) return authError(401, 'session_refresh_required');
          return backendError(error);
        }
      }
      if (path === 'refresh') {
        let invalidBackendSession = false;
        try {
          const successor = await store.refresh(id, async refreshCookie => {
            let refreshed;
            try { refreshed = await backend.refresh(refreshCookie); }
            catch (error) { invalidBackendSession = error instanceof BackendFailure && error.status === 401; throw error; }
            if (refreshed.expiresAt.getTime() !== metadata.expiresAt.getTime()) throw new BackendFailure();
            return refreshed.credentials;
          });
          return cookie(response({ authenticated: true }), successor, metadata.expiresAt);
        } catch {
          // Do not retry, recover successors, or claim that an uncertain attempt
          // is reusable. Source protocol fences the old identifier durably.
          return cookie(authError(invalidBackendSession ? 401 : 503,
            invalidBackendSession ? 'session_required' : 'reauthentication_required'));
        }
      }
      try {
        return await store.withAccess(id, async access => path === 'session' ?
          response({ authenticated: true, capabilities: await backend.capabilities(access), expires_at: metadata.expiresAt.toISOString() }) :
          response(await backend.vendorStatus(access)));
      } catch (error) {
        if (error instanceof SessionAccessExpired) return authError(401, 'session_refresh_required');
        if (error instanceof BackendFailure && error.status === 401) return authError(401, 'session_refresh_required');
        return backendError(error);
      }
    } catch (error) { return backendError(error); }
  };
}
