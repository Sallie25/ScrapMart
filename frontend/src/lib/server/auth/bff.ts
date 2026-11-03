import 'server-only';
import { BackendAuthClient, BackendFailure, boundedJson, exactHttpsOrigin } from './backend';
import { buyerRegistration, vendorRegistration, login, acknowledgment, safeFields } from './contracts';
import type { Role } from './contracts';
import { hashIdentifier } from '../sessions/crypto';
import { browserSessionCookie } from '../sessions/index';
import type { SessionStore } from '../sessions/store';

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
    403: 'forbidden', 413: 'request_too_large', 415: 'json_required', 422: 'validation_error',
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
    const read = path === 'session' || path === 'vendor/status';
    if (!registration && !signingIn && !read && path !== 'refresh' && path !== 'logout') return authError(404, 'not_found');
    if (request.method !== (read ? 'GET' : 'POST')) return authError(405, 'method_not_allowed');
    if (!dependencies || !origin) return authError(503, 'authentication_disabled');
    const { store, backend } = dependencies;
    if (!read && (request.headers.get('origin') !== origin || new URL(request.url).origin !== origin ||
        request.headers.get('x-scrapmart-csrf') !== '1' ||
        (request.headers.has('sec-fetch-site') && request.headers.get('sec-fetch-site') !== 'same-origin'))) {
      return authError(403, 'origin_or_csrf_rejected');
    }
    try {
      if (!read && !registration && !signingIn && request.body) {
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
        if (error instanceof BackendFailure && error.status === 401) return authError(401, 'session_refresh_required');
        return backendError(error);
      }
    } catch (error) { return backendError(error); }
  };
}
