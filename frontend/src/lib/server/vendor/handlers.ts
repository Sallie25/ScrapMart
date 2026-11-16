import 'server-only';
import { hashIdentifier } from '../sessions/crypto';
import { browserSessionCookie } from '../sessions/index';
import { SessionAccessExpired, type SessionStore } from '../sessions/store';
import type { HttpTransport } from '../auth/backend';

const headers = { 'Cache-Control': 'no-store', 'Vary': 'Cookie', 'X-Content-Type-Options': 'nosniff' };
const id = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/;
const failure = (status: number, code: string) => Response.json({ detail: { code, message: 'Vendor request could not be completed.' } }, { status, headers });

async function bytes(stream: ReadableStream<Uint8Array> | null, max: number): Promise<Buffer> {
  if (!stream) return Buffer.alloc(0);
  const reader = stream.getReader(); const chunks: Buffer[] = []; let size = 0;
  try {
    while (true) {
      const part = await reader.read(); if (part.done) break;
      size += part.value.byteLength;
      if (size > max) throw new Error('too_large');
      chunks.push(Buffer.from(part.value));
    }
    return Buffer.concat(chunks, size);
  } finally { void reader.cancel().catch(() => {}); reader.releaseLock(); }
}

function route(operation: readonly string[], method: string) {
  const path = operation.join('/');
  if (path === 'buyer/orders' && ['GET', 'POST'].includes(method)) return '/api/v1/buyer/orders';
  if (path === 'vendor/orders' && method === 'GET') return '/api/v1/vendor/orders';
  if (['buyer', 'vendor'].includes(operation[0]) && operation[1] === 'orders' && id.test(operation[2] ?? '')) {
    if (operation.length === 3 && method === 'GET') return `/api/v1/${operation[0]}/orders/${operation[2]}`;
    const actions = operation[0] === 'buyer' ? ['cancel', 'complete'] : ['accept', 'reject', 'prepare', 'deliver'];
    if (operation.length === 4 && method === 'POST' && actions.includes(operation[3]))
      return `/api/v1/${operation[0]}/orders/${operation[2]}/${operation[3]}`;
  }
  if (path === 'conversations' && ['GET', 'POST'].includes(method)) return '/api/v1/conversations';
  if (path === 'conversations/unread' && method === 'GET') return '/api/v1/conversations/unread';
  if (operation[0] === 'conversations' && id.test(operation[1] ?? '')) {
    if (operation.length === 3 && operation[2] === 'messages' && ['GET', 'POST'].includes(method))
      return `/api/v1/conversations/${operation[1]}/messages`;
    if (operation.length === 3 && operation[2] === 'read' && method === 'POST')
      return `/api/v1/conversations/${operation[1]}/read`;
  }
  if (path === 'onboarding' && ['GET', 'PATCH'].includes(method)) return '/api/v1/auth/vendor/onboarding';
  if (path === 'identity-document' && method === 'POST') return '/api/v1/auth/vendor/identity-document';
  if (path === 'phone/send-code' && method === 'POST') return '/api/v1/auth/phone/send-code';
  if (path === 'phone/verify-code' && method === 'POST') return '/api/v1/auth/phone/verify-code';
  if (path === 'listings' && ['GET', 'POST'].includes(method)) return '/api/v1/vendor/listings';
  if (operation[0] !== 'listings' || !id.test(operation[1] ?? '')) return null;
  if (operation.length === 2 && ['GET', 'PATCH', 'DELETE'].includes(method)) return `/api/v1/vendor/listings/${operation[1]}`;
  if (operation.length === 3 && method === 'POST' && ['publish', 'pause', 'sold', 'photos'].includes(operation[2]))
    return `/api/v1/vendor/listings/${operation[1]}/${operation[2]}`;
  return null;
}

function expectedStatus(path: string, method: string): number {
  if (method === 'DELETE' || path.endsWith('/verify-code')) return 204;
  if (path.endsWith('/identity-document') || path.endsWith('/send-code')) return 202;
  if (method === 'POST' && (path === '/api/v1/vendor/listings' || path === '/api/v1/buyer/orders' ||
    path === '/api/v1/conversations' || path.endsWith('/photos') || path.endsWith('/messages'))) return 201;
  return 200;
}

export function createVendorHandlers(deps?: { store: SessionStore; backendOrigin: string; browserOrigin: string; transport: HttpTransport }) {
  return async function handle(request: Request, operation: readonly string[]): Promise<Response> {
    const path = route(operation, request.method);
    if (!path) return failure(404, 'not_found');
    if (!deps) return failure(503, 'authentication_disabled');
    const mutating = request.method !== 'GET';
    if (mutating && (request.headers.get('origin') !== deps.browserOrigin || new URL(request.url).origin !== deps.browserOrigin ||
      request.headers.get('x-scrapmart-csrf') !== '1' ||
      (request.headers.has('sec-fetch-site') && request.headers.get('sec-fetch-site') !== 'same-origin')))
      return failure(403, 'origin_or_csrf_rejected');
    const cookie = (request.headers.get('cookie') ?? '').split(';').map(value => value.trim())
      .filter(value => value.split('=', 1)[0] === browserSessionCookie.name);
    if (cookie.length !== 1) return failure(401, 'session_required');
    const identifier = cookie[0].slice(cookie[0].indexOf('=') + 1);
    try { hashIdentifier(identifier); } catch { return failure(401, 'session_required'); }
    const incoming = new URL(request.url);
    const allowedQuery = path.endsWith('/listings') && request.method === 'GET' ? ['limit', 'cursor', 'status'] :
      (path.endsWith('/orders') || path === '/api/v1/conversations' || path.endsWith('/messages')) && request.method === 'GET' ? ['limit', 'cursor'] :
      path.endsWith('/photos') ? ['public_consent'] : path.endsWith('/identity-document') ? ['identification_type'] : [];
    if ([...incoming.searchParams.keys()].some(key => !allowedQuery.includes(key) || incoming.searchParams.getAll(key).length !== 1) ||
      path.endsWith('/photos') && incoming.searchParams.get('public_consent') !== 'true' ||
      path.endsWith('/identity-document') && !['national_id', 'passport', 'drivers_license', 'voter_id'].includes(incoming.searchParams.get('identification_type') ?? '')) return failure(422, 'validation_error');
    const binary = path.endsWith('/photos') || path.endsWith('/identity-document');
    if (binary && !['image/jpeg', 'image/png'].includes(request.headers.get('content-type') ?? '')) return failure(415, 'unsupported_media_type');
    if (mutating && !binary && request.method !== 'DELETE' &&
      request.headers.get('content-type')?.split(';', 1)[0] !== 'application/json') return failure(415, 'json_required');
    let body: Buffer | undefined;
    try { if (mutating && request.body) body = await bytes(request.body, binary ? 3 * 1024 * 1024 : 16384); }
    catch { return failure(413, 'request_too_large'); }
    try {
      if (!await deps.store.lookup(identifier)) return failure(401, 'session_required');
      return await deps.store.withAccess(identifier, async access => {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 10000);
        try {
          const upstream = await deps.transport(new Request(deps.backendOrigin + path + incoming.search, {
            method: request.method, headers: { Authorization: `Bearer ${access}`,
              ...(mutating ? { Origin: deps.browserOrigin, 'X-ScrapMart-CSRF': '1' } : {}),
              ...(mutating && request.method !== 'DELETE' ? { 'Content-Type': request.headers.get('content-type') ?? 'application/json' } : {}) },
            body: body ? new Uint8Array(body) : undefined, cache: 'no-store', credentials: 'omit', redirect: 'error', signal: controller.signal,
          }));
          if (upstream.status === 204 && expectedStatus(path, request.method) === 204) return new Response(null, { status: 204, headers });
          if (upstream.ok && upstream.status !== expectedStatus(path, request.method)) return failure(502, 'backend_invalid_response');
          if (upstream.headers.get('content-type')?.split(';', 1)[0] !== 'application/json') return failure(502, 'backend_invalid_response');
          const payload = await bytes(upstream.body, 1024 * 1024);
          if (upstream.ok) {
            try { JSON.parse(payload.toString('utf8')); } catch { return failure(502, 'backend_invalid_response'); }
            return new Response(new Uint8Array(payload), { status: upstream.status, headers: { ...headers, 'Content-Type': 'application/json' } });
          }
          const status = [400, 401, 403, 404, 409, 422, 429, 503].includes(upstream.status) ? upstream.status : 502;
          return failure(status, upstream.status === 401 ? 'session_refresh_required' :
            status === 403 ? 'selling_forbidden' : status === 409 ? 'listing_conflict' :
            status === 422 ? 'validation_error' : 'vendor_request_failed');
        } finally { clearTimeout(timer); controller.abort(); }
      });
    } catch (error) {
      return failure(error instanceof SessionAccessExpired ? 401 : 503,
        error instanceof SessionAccessExpired ? 'session_refresh_required' : 'vendor_unavailable');
    }
  };
}
