import test from 'node:test';
import assert from 'node:assert/strict';
import { newIdentifier } from '../src/lib/server/sessions/crypto.ts';
import { createVendorHandlers } from '../src/lib/server/vendor/handlers.ts';
import { createVendorAuthClient } from '../src/lib/vendor-auth.ts';

const origin = 'https://scrapmart.test';
const backendOrigin = 'https://backend.scrapmart.test';
const browserId = newIdentifier();
const access = 'synthetic-access-token';
const request = (path, method = 'GET', body, extra = {}) => new Request(`${origin}/api/vendor/${path}`, {
  method, headers: { Cookie: `__Host-scrapmart_session=${browserId}`,
    ...(method !== 'GET' ? { Origin: origin, 'X-ScrapMart-CSRF': '1' } : {}),
    ...(body ? { 'Content-Type': 'application/json' } : {}), ...extra },
  body: body === undefined ? undefined : JSON.stringify(body),
});

test('Vendor signup and login use the authenticated BFF, without carrying shop draft fields', async () => {
  const calls = [];
  const client = createVendorAuthClient(async (path, init) => {
    calls.push({ path, init });
    return path.endsWith('/signup') ? Response.json({ message: 'If registration was successful, you can now sign in.' }, { status: 202 }) :
      Response.json({ authenticated: true });
  });
  const signup = { fullName: 'Ada Vendor', phone: '08012345678', email: 'ada@example.test',
    password: 'a sufficiently long password', businessName: 'Ada Metals', previewConsent: true };
  assert.equal((await client.signup(signup)).status, 'accepted');
  assert.equal(calls[0].path, '/api/auth/vendor/signup');
  assert.deepEqual(JSON.parse(calls[0].init.body), { full_name: signup.fullName, phone_number: signup.phone,
    email: signup.email, password: signup.password, business_name: signup.businessName });
  assert.equal((await client.login({ email: signup.email, password: signup.password })).status, 'authenticated');
  assert.equal(calls[1].path, '/api/auth/vendor/login');
});

test('Vendor bridge requires a session and origin/CSRF for mutations', async () => {
  let calls = 0;
  const handle = createVendorHandlers({ store: { lookup: async () => ({ expiresAt: new Date(Date.now() + 60000) }), withAccess: async (_id, callback) => callback(access) },
    backendOrigin, browserOrigin: origin, transport: async () => { calls++; return Response.json({}); } });
  assert.equal((await handle(new Request(`${origin}/api/vendor/listings`), ['listings'])).status, 401);
  assert.equal((await handle(request('listings', 'POST', { title: 'Metal' }, { Origin: 'https://evil.test' }), ['listings'])).status, 403);
  assert.equal((await handle(request('listings/../../auth/refresh'), ['listings', '..', '..', 'auth', 'refresh'])).status, 404);
  assert.equal(calls, 0);
});

test('Vendor bridge forwards only approved listing operations and keeps bearer private', async () => {
  const calls = [];
  const handle = createVendorHandlers({ store: { lookup: async () => ({ expiresAt: new Date(Date.now() + 60000) }), withAccess: async (_id, callback) => callback(access) },
    backendOrigin, browserOrigin: origin, transport: async upstream => {
      calls.push(upstream);
      assert.equal(upstream.headers.get('authorization'), `Bearer ${access}`);
      return Response.json({ id: 'synthetic-id', status: 'draft' }, { status: 201 });
    } });
  const result = await handle(request('listings', 'POST', { title: 'Metal' }), ['listings']);
  assert.equal(result.status, 201);
  assert.equal(calls[0].url, `${backendOrigin}/api/v1/vendor/listings`);
  assert.equal(result.headers.get('cache-control'), 'no-store');
  assert.ok(!(await result.text()).includes(access));
});

test('Vendor bridge maps denied publication without reporting success', async () => {
  const handle = createVendorHandlers({ store: { lookup: async () => ({ expiresAt: new Date(Date.now() + 60000) }), withAccess: async (_id, callback) => callback(access) },
    backendOrigin, browserOrigin: origin, transport: async () => Response.json({ detail: { code: 'selling_forbidden' } }, { status: 403 }) });
  const id = '12345678-1234-1234-1234-123456789abc';
  const result = await handle(request(`listings/${id}/publish`, 'POST', { public_location_consent: true }), ['listings', id, 'publish']);
  assert.equal(result.status, 403);
  assert.equal((await result.json()).detail.code, 'selling_forbidden');
});

test('Buyer order and conversation requests use only approved backend routes', async () => {
  const paths = [];
  const handle = createVendorHandlers({ store: { lookup: async () => ({ expiresAt: new Date(Date.now() + 60000) }), withAccess: async (_id, callback) => callback(access) },
    backendOrigin, browserOrigin: origin, transport: async upstream => {
      paths.push(new URL(upstream.url).pathname);
      return Response.json({ id: 'synthetic-id' }, { status: 201 });
    } });
  assert.equal((await handle(request('buyer/orders', 'POST', { listing_id: '123', request_id: '456', quantity: '1' }), ['buyer', 'orders'])).status, 201);
  assert.equal((await handle(request('conversations', 'POST', { listing_id: '123' }), ['conversations'])).status, 201);
  assert.deepEqual(paths, ['/api/v1/buyer/orders', '/api/v1/conversations']);
  assert.equal((await handle(request('buyer/orders/admin', 'POST', {}), ['buyer', 'orders', 'admin'])).status, 404);
});

test('image uploads accept the backend 3 MB boundary and reject larger bodies before forwarding', async () => {
  let calls = 0;
  const handle = createVendorHandlers({ store: { lookup: async () => ({ expiresAt: new Date(Date.now() + 60000) }), withAccess: async (_id, callback) => callback(access) },
    backendOrigin, browserOrigin: origin, transport: async upstream => {
      calls++;
      assert.equal((await upstream.arrayBuffer()).byteLength, 3 * 1024 * 1024);
      return Response.json({ id: 'synthetic-photo' }, { status: 201 });
    } });
  const listing = '12345678-1234-1234-1234-123456789abc';
  const upload = size => new Request(`${origin}/api/vendor/listings/${listing}/photos?public_consent=true`, {
    method: 'POST', headers: { Cookie: `__Host-scrapmart_session=${browserId}`, Origin: origin,
      'X-ScrapMart-CSRF': '1', 'Content-Type': 'image/jpeg' }, body: new Uint8Array(size),
  });
  assert.equal((await handle(upload(3 * 1024 * 1024 + 1), ['listings', listing, 'photos'])).status, 413);
  assert.equal(calls, 0);
  assert.equal((await handle(upload(3 * 1024 * 1024), ['listings', listing, 'photos'])).status, 201);
  assert.equal(calls, 1);
});

test('photos require explicit public consent and JPEG or PNG before any upstream action', async () => {
  const handle = createVendorHandlers({ store: {}, backendOrigin, browserOrigin: origin,
    transport: async () => assert.fail('Invalid upload must not reach backend') });
  const listing = '12345678-1234-1234-1234-123456789abc';
  const upload = (query, type) => new Request(`${origin}/api/vendor/listings/${listing}/photos${query}`, {
    method: 'POST', headers: { Cookie: `__Host-scrapmart_session=${browserId}`, Origin: origin,
      'X-ScrapMart-CSRF': '1', 'Content-Type': type }, body: new Uint8Array(10),
  });
  assert.equal((await handle(upload('', 'image/jpeg'), ['listings', listing, 'photos'])).status, 422);
  assert.equal((await handle(upload('?public_consent=true', 'image/svg+xml'), ['listings', listing, 'photos'])).status, 415);
});
