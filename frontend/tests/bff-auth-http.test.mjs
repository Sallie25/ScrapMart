import test from 'node:test';
import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';
import { BackendAuthClient, backendRefreshCookie } from '../src/lib/server/auth/backend.ts';
import { createBffHandlers } from '../src/lib/server/auth/bff.ts';
import { SessionStore } from '../src/lib/server/sessions/store.ts';
import { CredentialVault, newIdentifier, hashIdentifier } from '../src/lib/server/sessions/crypto.ts';
import { DatabaseDouble } from './helpers/session-pg-double.mjs';
import { GET, POST, OPTIONS } from '../src/app/api/auth/[...operation]/route.ts';

assert.notEqual(process.env.SCRAPMART_BFF_ISOLATED_TEST, '1', 'HTTP tests must never use real PostgreSQL');
const origin = 'https://scrapmart.test';
const backendOrigin = 'https://backend.scrapmart.test';
const password = 'Synthetic passphrase only';
const access = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJzeW50aGV0aWMifQ.c3ludGhldGlj';
const ack = 'If registration was successful, you can now sign in.';
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
function json(value, status = 200, headers = {}) {
  return Response.json(value, { status, headers });
}
function tokenReply(refresh, expiry, overrides = {}) {
  return json({ access_token: access, token_type: 'bearer', expires_in: 900 }, 200, {
    'Set-Cookie': `${backendRefreshCookie}=${refresh}; Path=/api/v1/auth; Secure; HttpOnly; SameSite=Lax; Expires=${expiry.toUTCString()}; Max-Age=3599`,
    ...overrides,
  });
}
function request(path, { body, cookie, method = 'POST', headers = {} } = {}) {
  return new Request(origin + '/api/auth/' + path, { method, headers: {
    ...(method === 'POST' ? { Origin: origin, 'X-ScrapMart-CSRF': '1' } : {}),
    ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    ...(cookie ? { Cookie: `__Host-scrapmart_session=${cookie}` } : {}), ...headers,
  }, body: body === undefined ? undefined : JSON.stringify(body) });
}
function browserId(response) {
  return response.headers.get('set-cookie')?.split(';', 1)[0].split('=')[1];
}
function fixture(transport, timeoutMs = 1000) {
  const db = new DatabaseDouble(); const store = new SessionStore(db.settings,
    new CredentialVault('v1', { v1: randomBytes(32) }));
  const calls = []; const expires = new Date(Math.floor((Date.now() + 3600000) / 1000) * 1000);
  const refresh = newIdentifier();
  const backend = new BackendAuthClient({ origin: backendOrigin, browserOrigin: origin, timeoutMs,
    transport: async req => { calls.push(req); return transport(req, { refresh, expires }); } });
  const handle = createBffHandlers({ store, backend, browserOrigin: origin });
  return { db, store, backend, calls, expires, refresh,
    send: (path, options) => handle(request(path, options), path.split('/')) };
}
const signup = { email: 'buyer@example.test', password, full_name: 'Synthetic Buyer', phone_number: null };
const login = { email: signup.email, password };
async function seed(f) {
  return f.store.create({ accessToken: access, refreshCookie: f.refresh,
    accessExpiresAt: new Date(Date.now() + 60000).toISOString() }, f.expires);
}
async function assertPrivate(response, f) {
  const body = await response.clone().text();
  assert.ok(!body.includes(access) && !body.includes(f.refresh) && !body.includes(password));
  assert.equal(response.headers.get('cache-control'), 'no-store');
  assert.equal(response.headers.has('access-control-allow-origin'), false);
}

test('production Next route is disabled without constructing dependencies or using fetch', async () => {
  const previous = globalThis.fetch;
  globalThis.fetch = () => assert.fail('No live transport allowed');
  try {
    for (const [handler, path, options] of [[POST, 'buyer/login', { body: login }], [GET, 'session', { method: 'GET' }]]) {
      const result = await handler(request(path, options), { params: Promise.resolve({ operation: path.split('/') }) });
      assert.equal(result.status, 503); assert.equal(result.headers.has('set-cookie'), false);
      assert.equal((await result.json()).detail.code, 'authentication_disabled');
    }
    assert.equal(OPTIONS().status, 405);
  } finally { globalThis.fetch = previous; }
});

test('Buyer and Vendor registration forward exact snake_case payloads without sessions or cookies', async () => {
  const f = fixture(async req => {
    assert.equal(req.method, 'POST'); assert.equal(req.headers.get('origin'), origin);
    assert.equal(req.headers.get('x-scrapmart-csrf'), '1');
    assert.equal(req.headers.has('cookie'), false); assert.equal(req.headers.has('authorization'), false);
    const body = await req.json(); assert.equal(body.full_name, signup.full_name);
    assert.equal(body.password, password); assert.equal(body.email, signup.email);
    if (req.url.endsWith('/vendor/signup')) assert.equal(body.business_name, 'Synthetic Shop');
    return json({ message: ack }, 202, { 'Set-Cookie': 'untrusted=ignored' });
  });
  for (const role of ['buyer', 'vendor']) {
    const result = await f.send(role + '/signup', { body: { ...signup, ...(role === 'vendor' ? { business_name: 'Synthetic Shop' } : {}) } });
    assert.equal(result.status, 202); assert.deepEqual(await result.json(), { message: ack });
    assert.equal(result.headers.has('set-cookie'), false); assert.equal(f.db.rows.length, 0);
  }
});

test('strict registration validation rejects role/approval injection, invalid passwords, text and non-ASCII email', async () => {
  const f = fixture(() => assert.fail('Invalid input reached backend'));
  const invalid = [ { role: 'admin' }, { verification_status: 'approved' }, { password: 'short' },
    { full_name: 'x'.repeat(151) }, { phone_number: 'x'.repeat(21) }, { email: 'K@example.test' },
    { full_name: '\ud800' }, { full_name: '\u001c'.repeat(5) }, { full_name: '\u205f' },
    { phone_number: '\u205f' }, { email: 'no-at-sign' } ];
  for (const change of invalid) {
    const response = await f.send('buyer/signup', { body: { ...signup, ...change } });
    assert.equal(response.status, 422); await assertPrivate(response, f);
    assert.ok(!(await response.text()).includes('verification_status'));
  }
  assert.equal((await f.send('vendor/signup', { body: signup })).status, 422);
  assert.equal((await f.send('vendor/signup', { body: { ...signup, business_name: 'x'.repeat(201) } })).status, 422);
  assert.equal((await f.send('vendor/signup', { body: { ...signup, business_name: '\u205f' } })).status, 422);
  assert.equal(f.calls.length, 0);
});

test('payload mapping preserves Unicode password/code points and canonicalizes ASCII email boundaries', async () => {
  const p = '  ' + '😀'.repeat(15) + '  ';
  const f = fixture(async req => {
    const body = await req.json(); assert.equal(body.password, p); assert.equal(body.email, 'buyer@example.test');
    assert.equal([...body.full_name].length, 150); return json({ message: ack }, 202);
  });
  const result = await f.send('buyer/signup', { body: { ...signup, email: ' \tBUYER@EXAMPLE.TEST\r', password: p, full_name: '😀'.repeat(150) } });
  assert.equal(result.status, 202);
});

test('Origin, CSRF and fetch metadata reject before transport or store operations', async () => {
  const f = fixture(() => assert.fail());
  for (const headers of [{ Origin: 'https://evil.test' }, { Origin: '' }, { 'X-ScrapMart-CSRF': '' },
    { 'X-ScrapMart-CSRF': '1, 1' }, { 'Sec-Fetch-Site': 'cross-site' }]) {
    assert.equal((await f.send('buyer/login', { body: login, headers })).status, 403);
    assert.equal((await f.send('logout', { headers })).status, 403);
  }
  assert.equal(f.calls.length, 0); assert.equal(f.db.calls.length, 0);
});

test('non-JSON and oversized/malformed bodies are rejected without reflecting inputs', async () => {
  const f = fixture(() => assert.fail());
  assert.equal((await f.send('buyer/signup', { body: signup, headers: { 'Content-Type': 'text/plain' } })).status, 415);
  assert.equal((await f.send('buyer/signup', { body: { ...signup, full_name: 'x'.repeat(17000) } })).status, 413);
  const handle = createBffHandlers({ store: f.store, backend: f.backend, browserOrigin: origin });
  const malformed = new Request(origin + '/api/auth/buyer/login', { method: 'POST', body: '{', headers: {
    Origin: origin, 'X-ScrapMart-CSRF': '1', 'Content-Type': 'application/json' } });
  assert.equal((await handle(malformed, ['buyer', 'login'])).status, 422);
});

test('login failure is generic and never creates a local session', async () => {
  const f = fixture(() => json({ detail: { message: 'sensitive upstream text', fields: [] } }, 401));
  const result = await f.send('buyer/login', { body: login });
  assert.equal(result.status, 401); assert.equal(result.headers.has('set-cookie'), false);
  assert.ok(!(await result.clone().text()).includes('sensitive')); assert.equal(f.db.rows.length, 0);
  await assertPrivate(result, f);
});

test('login creates encrypted durable records and hands off only an opaque host-only browser cookie', async () => {
  const f = fixture((req, data) => tokenReply(data.refresh, data.expires));
  const result = await f.send('buyer/login', { body: login });
  assert.equal(result.status, 200); assert.deepEqual(await result.clone().json(), { authenticated: true });
  const id = browserId(result); assert.equal(id.length, 43); assert.notEqual(id, f.refresh);
  assert.ok(await f.store.lookup(id)); assert.equal(f.db.row.hash, hashIdentifier(id));
  const header = result.headers.get('set-cookie');
  for (const flag of ['Secure', 'HttpOnly', 'SameSite=Lax', 'Path=/']) assert.ok(header.includes(flag));
  assert.ok(!header.includes('Domain=') && !header.includes(backendRefreshCookie));
  assert.ok(!JSON.stringify(f.db.rows).includes(access)); await assertPrivate(result, f);
});

test('existing browser identity requires explicit logout before account switching', async () => {
  const f = fixture(() => assert.fail()); const id = await seed(f);
  assert.equal((await f.send('vendor/login', { body: login, cookie: id })).status, 409);
  assert.equal(f.calls.length, 0); assert.ok(await f.store.lookup(id));
});

test('refresh uses only the backend cookie and rotates the browser ID without extending expiry', async () => {
  const replacement = newIdentifier();
  const f = fixture(async req => {
    assert.equal(req.url, backendOrigin + '/api/v1/auth/refresh');
    assert.equal(req.headers.get('cookie'), `${backendRefreshCookie}=${f.refresh}`);
    assert.equal(req.headers.has('authorization'), false); assert.equal(await req.text(), '');
    return tokenReply(replacement, f.expires);
  });
  const old = await seed(f); const result = await f.send('refresh', { cookie: old });
  assert.equal(result.status, 200); const successor = browserId(result); assert.notEqual(successor, old);
  assert.equal(await f.store.lookup(old), null); assert.equal((await f.store.lookup(successor)).expiresAt.getTime(), f.expires.getTime());
  await assertPrivate(result, f); assert.equal(f.calls.length, 1);
});

test('concurrent refresh requests dispatch at most one backend request', async () => {
  const entered = deferred(), release = deferred();
  const f = fixture(async () => { entered.resolve(); await release.promise; return tokenReply(newIdentifier(), f.expires); });
  const id = await seed(f); const first = f.send('refresh', { cookie: id });
  await entered.promise; const second = await f.send('refresh', { cookie: id });
  assert.equal(second.status, 401); release.resolve(); assert.equal((await first).status, 200);
  assert.equal(f.calls.length, 1);
});

test('lost upstream refresh responses fence the old ID without any retry', async () => {
  const f = fixture(() => { throw new Error('synthetic lost response with credential context'); });
  const id = await seed(f); const result = await f.send('refresh', { cookie: id });
  assert.equal(result.status, 503); assert.equal(browserId(result), ''); assert.equal(await f.store.lookup(id), null);
  assert.equal((await f.send('refresh', { cookie: id })).status, 401); assert.equal(f.calls.length, 1);
  await assertPrivate(result, f);
});

test('lost commit acknowledgment and failed quarantine cannot hand off an undisclosed successor', async () => {
  const f = fixture(() => tokenReply(newIdentifier(), f.expires)); const id = await seed(f);
  f.db.loseFinish = true; f.db.failQuarantine = true;
  const result = await f.send('refresh', { cookie: id });
  assert.equal(result.status, 503); assert.equal(browserId(result), '');
  assert.equal(await f.store.lookup(id), null); assert.equal(f.db.row.status, 'retired');
});

test('changed refresh expiry is rejected and requires reauthentication', async () => {
  const f = fixture(() => tokenReply(newIdentifier(), new Date(f.expires.getTime() + 60000)));
  const id = await seed(f); assert.equal((await f.send('refresh', { cookie: id })).status, 503);
  assert.equal(await f.store.lookup(id), null);
});

test('logout sends the backend cookie once, revokes locally and clears the browser cookie', async () => {
  const f = fixture(req => {
    assert.equal(req.url, backendOrigin + '/api/v1/auth/logout');
    assert.equal(req.headers.get('cookie'), `${backendRefreshCookie}=${f.refresh}`);
    assert.equal(req.headers.has('authorization'), false);
    return new Response(null, { status: 204 });
  });
  const id = await seed(f); const result = await f.send('logout', { cookie: id });
  assert.equal(result.status, 204); assert.equal(browserId(result), ''); assert.equal(await f.store.lookup(id), null);
  assert.equal(f.calls.length, 1); assert.equal(f.db.row.status, 'revoked');
  assert.equal((await f.send('logout')).status, 204);
});

test('logout backend outage still revokes local family but reports unconfirmed revocation', async () => {
  const f = fixture(() => { throw new Error('synthetic outage'); }); const id = await seed(f);
  const result = await f.send('logout', { cookie: id });
  assert.equal(result.status, 503); assert.equal((await result.json()).detail.code, 'logout_unconfirmed');
  assert.equal(await f.store.lookup(id), null); assert.equal(f.db.row.status, 'revoked');
});

test('logout during refresh blocks a late browser-cookie successor without falsely confirming backend logout', async () => {
  const entered = deferred(), release = deferred();
  const f = fixture(async req => {
    assert.ok(req.url.endsWith('/refresh')); entered.resolve(); await release.promise;
    return tokenReply(newIdentifier(), f.expires);
  });
  const id = await seed(f); const pending = f.send('refresh', { cookie: id });
  await entered.promise; const logout = await f.send('logout', { cookie: id });
  assert.equal(logout.status, 503); release.resolve(); assert.equal((await pending).status, 503);
  assert.equal(f.db.row.status, 'revoked'); assert.equal(f.calls.length, 1);
});

test('session discovery projects backend capabilities and does not infer Vendor approval from login role', async () => {
  const f = fixture(req => {
    assert.equal(req.headers.get('authorization'), `Bearer ${access}`);
    assert.equal(req.headers.has('cookie'), false);
    return json({ buyer: true, vendor: true, vendor_verification_status: 'pending' });
  });
  const id = await seed(f); const result = await f.send('session', { method: 'GET', cookie: id,
    headers: { Authorization: 'Bearer untrusted-browser-token' } });
  assert.equal(result.status, 200); const body = await result.clone().json();
  assert.equal(body.capabilities.vendor_verification_status, 'pending'); assert.equal('can_sell' in body, false);
  await assertPrivate(result, f);
});

test('Vendor status preserves every recognized state and projects no private profile fields', async () => {
  for (const verification_status of ['pending', 'approved', 'rejected', 'suspended']) {
    const f = fixture(() => json({ business_name: 'Synthetic Shop', verification_status,
      full_name: 'Synthetic Person', email: 'vendor@example.test', phone_number: null, created_at: new Date().toISOString() }));
    const id = await seed(f); const result = await f.send('vendor/status', { method: 'GET', cookie: id });
    assert.deepEqual(await result.json(), { verification_status });
  }
});

test('Buyer login never falls back to Vendor login and Vendor-only reads preserve 403', async () => {
  const f = fixture(req => {
    assert.ok(req.url.endsWith('/buyer/login') || req.url.endsWith('/vendor/me'));
    return json({ detail: { fields: [] } }, req.url.endsWith('/buyer/login') ? 401 : 403);
  });
  assert.equal((await f.send('buyer/login', { body: login })).status, 401);
  const id = await seed(f); assert.equal((await f.send('vendor/status', { method: 'GET', cookie: id })).status, 403);
});

test('Vendor login uses its exact endpoint and never claims approval', async () => {
  const f = fixture(req => { assert.ok(req.url.endsWith('/vendor/login')); return tokenReply(f.refresh, f.expires); });
  const result = await f.send('vendor/login', { body: login }); assert.equal(result.status, 200);
  assert.deepEqual(await result.json(), { authenticated: true });
});

test('backend rate-limit fields are allowlisted and credential-bearing error messages are discarded', async () => {
  const f = fixture(() => json({ detail: { message: password, fields: ['password', 'private_token'] } }, 429, { 'Retry-After': '60' }));
  const result = await f.send('buyer/login', { body: login });
  assert.equal(result.status, 429); assert.equal(result.headers.get('retry-after'), '60');
  assert.deepEqual((await result.clone().json()).detail.fields, ['password']); await assertPrivate(result, f);
});

test('unsafe backend cookie scope, missing cookie, duplicate cookies and unexpected token fields fail closed', async () => {
  for (const bad of ['; Domain=backend.scrapmart.test', '; Path=/', '; SameSite=None']) {
    const f = fixture(() => tokenReply(f.refresh, f.expires, { 'Set-Cookie':
      `${backendRefreshCookie}=${f.refresh}; Path=/api/v1/auth; Secure; HttpOnly; SameSite=Lax; Max-Age=3600; Expires=${f.expires.toUTCString()}${bad}` }));
    assert.equal((await f.send('buyer/login', { body: login })).status, 503); assert.equal(f.db.rows.length, 0);
  }
  const missing = fixture(() => json({ access_token: access, token_type: 'bearer', expires_in: 900 }));
  assert.equal((await missing.send('buyer/login', { body: login })).status, 503);
  const duplicate = fixture(() => {
    const res = tokenReply(duplicate.refresh, duplicate.expires);
    res.headers.append('Set-Cookie', res.headers.get('set-cookie')); return res;
  });
  assert.equal((await duplicate.send('buyer/login', { body: login })).status, 503);
  const extra = fixture(() => json({ access_token: access, token_type: 'bearer', expires_in: 900, refresh_token: 'not allowed' }));
  assert.equal((await extra.send('buyer/login', { body: login })).status, 503);
});

test('storage failures cannot create a browser login and trigger best-effort backend cleanup', async () => {
  const f = fixture(req => req.url.endsWith('/logout') ? new Response(null, { status: 204 }) : tokenReply(f.refresh, f.expires));
  f.db.outage = true; const result = await f.send('buyer/login', { body: login });
  assert.equal(result.status, 503); assert.equal(result.headers.has('set-cookie'), false);
  assert.equal(f.calls.length, 2);
});

test('database outages fail session discovery closed without contacting the backend', async () => {
  const f = fixture(() => assert.fail()); const id = await seed(f); f.db.outage = true;
  assert.equal((await f.send('session', { method: 'GET', cookie: id })).status, 503); assert.equal(f.calls.length, 0);
});

test('duplicate browser cookies cannot select an account or dispatch credentials', async () => {
  const f = fixture(() => assert.fail()); const id = await seed(f);
  const result = await f.send('session', { method: 'GET', headers: {
    Cookie: `__Host-scrapmart_session=${id}; __Host-scrapmart_session=${newIdentifier()}` } });
  assert.equal(result.status, 400); assert.equal(f.calls.length, 0);
});

test('backend timeouts and redirects fail closed without a network fallback or retry', async () => {
  const timed = fixture(() => new Promise(() => {}), 20);
  assert.equal((await timed.send('buyer/login', { body: login })).status, 503); assert.equal(timed.calls.length, 1);
  const redirect = fixture(() => new Response(null, { status: 302, headers: { Location: 'https://evil.test' } }));
  assert.equal((await redirect.send('buyer/login', { body: login })).status, 503); assert.equal(redirect.calls.length, 1);
});

test('stale backend bearer responses request explicit refresh without automatic mutation on GET', async () => {
  const f = fixture(() => json({ detail: { fields: [] } }, 401)); const id = await seed(f);
  const result = await f.send('session', { method: 'GET', cookie: id });
  assert.equal(result.status, 401); assert.equal((await result.json()).detail.code, 'session_refresh_required');
  assert.equal(result.headers.has('set-cookie'), false); assert.equal(f.calls.length, 1); assert.ok(await f.store.lookup(id));
});

test('invalid backend refresh credentials return 401 and permanently block the local identifier', async () => {
  const f = fixture(() => json({ detail: { fields: [] } }, 401)); const id = await seed(f);
  const result = await f.send('refresh', { cookie: id });
  assert.equal(result.status, 401); assert.equal(browserId(result), ''); assert.equal(await f.store.lookup(id), null);
});

test('refresh and logout reject body credentials before store or backend operations', async () => {
  const f = fixture(() => assert.fail());
  for (const path of ['refresh', 'logout']) {
    const response = await f.send(path, { body: { refresh_token: 'never accepted' } });
    assert.equal(response.status, 400);
  }
  assert.equal(f.db.calls.length, 0); assert.equal(f.calls.length, 0);
});

test('a stalled backend response body is bounded by the same request deadline', async () => {
  let canceled = false;
  const f = fixture(() => new Response(new ReadableStream({ cancel() { canceled = true; } }),
    { status: 200, headers: { 'Content-Type': 'application/json' } }), 20);
  assert.equal((await f.send('buyer/login', { body: login })).status, 503);
  assert.equal(canceled, true); assert.equal(f.calls.length, 1);
});

test('logout storage failure never reports confirmed revocation or dispatches credentials', async () => {
  const f = fixture(() => assert.fail()); const id = await seed(f); f.db.outage = true;
  const result = await f.send('logout', { cookie: id });
  assert.equal(result.status, 503); assert.equal((await result.json()).detail.code, 'logout_unconfirmed');
  assert.equal(f.calls.length, 0);
});

test('expired access credentials do not trigger implicit refresh on session discovery', async () => {
  const f = fixture(() => assert.fail());
  const id = await f.store.create({ accessToken: access, refreshCookie: f.refresh,
    accessExpiresAt: new Date(0).toISOString() }, f.expires);
  const result = await f.send('session', { method: 'GET', cookie: id });
  assert.equal(result.status, 401); assert.equal((await result.json()).detail.code, 'session_refresh_required');
  assert.equal(f.calls.length, 0); assert.ok(await f.store.lookup(id));
});

test('unknown Vendor status cannot become an approval or capability grant', async () => {
  const f = fixture(() => json({ buyer: false, vendor: true, vendor_verification_status: 'trusted' }));
  const id = await seed(f); assert.equal((await f.send('session', { method: 'GET', cookie: id })).status, 503);
});

test('an unexpected logout success format is not treated as confirmed revocation', async () => {
  const f = fixture(() => json(null, 200)); const id = await seed(f);
  assert.equal((await f.send('logout', { cookie: id })).status, 503);
  assert.equal(await f.store.lookup(id), null);
});

test('server-side transport never forwards browser credentials or arbitrary upstream locations', async () => {
  const f = fixture(req => {
    assert.equal(new URL(req.url).origin, backendOrigin); assert.equal(req.redirect, 'error');
    assert.equal(req.credentials, 'omit'); assert.equal(req.cache, 'no-store');
    assert.equal(req.headers.has('cookie'), false); assert.equal(req.headers.has('authorization'), false);
    return json({ message: ack }, 202);
  });
  assert.equal((await f.send('buyer/signup', { body: signup, headers: {
    Authorization: 'Bearer browser-secret', Cookie: 'untrusted=browser-cookie', 'X-Forwarded-For': '192.0.2.1' } })).status, 202);
  assert.equal(f.calls[0].headers.has('x-forwarded-for'), false);
});

test('revoked browser sessions cannot discover capabilities and repeated known-cookie logout stays honest', async () => {
  const f = fixture(() => new Response(null, { status: 204 })); const id = await seed(f);
  assert.equal((await f.send('logout', { cookie: id })).status, 204);
  assert.equal((await f.send('session', { method: 'GET', cookie: id })).status, 401);
  const repeated = await f.send('logout', { cookie: id });
  assert.equal(repeated.status, 503); assert.equal((await repeated.json()).detail.code, 'logout_unconfirmed');
  assert.equal(f.calls.length, 1); assert.equal((await f.send('logout')).status, 204);
});

test('capability discovery preserves Buyer-only, Vendor-only and shared experiences', async () => {
  for (const value of [
    { buyer: true, vendor: false, vendor_verification_status: null },
    { buyer: false, vendor: true, vendor_verification_status: 'suspended' },
    { buyer: true, vendor: true, vendor_verification_status: 'approved' },
  ]) {
    const f = fixture(req => {
      assert.equal(req.url, backendOrigin + '/api/v1/auth/capabilities');
      return json(value);
    });
    const id = await seed(f);
    const result = await f.send('session', { method: 'GET', cookie: id });
    assert.equal(result.status, 200);
    assert.deepEqual((await result.json()).capabilities, value);
    assert.equal(f.calls.length, 1);
  }
});

test('unsupported operations and methods never dispatch backend credentials', async () => {
  const f = fixture(() => assert.fail('Unsupported operation reached backend'));
  for (const path of ['buyer/login', 'vendor/signup', 'refresh', 'logout']) {
    assert.equal((await f.send(path, { method: 'GET' })).status, 405);
  }
  assert.equal((await f.send('session')).status, 405);
  assert.equal((await f.send('vendor/enroll', { body: { business_name: 'Test Shop', current_password: password } })).status, 401);
  assert.equal((await f.send('logout-all')).status, 404);
  assert.equal(f.calls.length, 0); assert.equal(f.db.calls.length, 0);
});

test('an aborted browser body is canceled before backend dispatch', async () => {
  const f = fixture(() => assert.fail('Aborted body reached backend'));
  const controller = new AbortController(); let canceled = false;
  const req = new Request(origin + '/api/auth/buyer/signup', {
    method: 'POST', signal: controller.signal, duplex: 'half',
    headers: { Origin: origin, 'X-ScrapMart-CSRF': '1', 'Content-Type': 'application/json' },
    body: new ReadableStream({ cancel() { canceled = true; } }),
  });
  const handle = createBffHandlers({ store: f.store, backend: f.backend, browserOrigin: origin });
  controller.abort();
  assert.equal((await handle(req, ['buyer', 'signup'])).status, 503);
  assert.equal(canceled, true); assert.equal(f.calls.length, 0);
});

test('vendor shop details use authenticated GET and CSRF-protected PATCH', async () => {
  const record = { business_name: 'Test Shop', shop_location: 'Ikeja', shop_address: 'Main Road', verification_status: 'pending' };
  const f = fixture(async req => {
    assert.equal(req.url, backendOrigin + '/api/v1/auth/vendor/onboarding');
    assert.equal(req.headers.get('authorization'), 'Bearer ' + access);
    if (req.method === 'PATCH') {
      assert.equal(req.headers.get('origin'), origin);
      assert.equal(req.headers.get('x-scrapmart-csrf'), '1');
      assert.deepEqual(await req.json(), { shop_location: 'Ikeja', shop_address: 'Main Road' });
    } else assert.equal(req.method, 'GET');
    return json(record);
  });
  const id = await seed(f);
  const read = await f.send('vendor/onboarding', { method: 'GET', cookie: id });
  assert.equal(read.status, 200);
  assert.deepEqual(await read.json(), record);
  const patch = await f.send('vendor/onboarding', { method: 'PATCH', cookie: id,
    body: { shop_location: 'Ikeja', shop_address: 'Main Road' },
    headers: { Origin: origin, 'X-ScrapMart-CSRF': '1' } });
  assert.equal(patch.status, 200);
  assert.equal(f.calls.length, 2);
});

test('vendor shop update rejects unauthorized and unsafe inputs without backend dispatch', async () => {
  const f = fixture(() => assert.fail('Unauthorized shop mutation reached backend'));
  const id = await seed(f);
  const body = { shop_location: 'Ikeja', shop_address: 'Main Road' };
  assert.equal((await f.send('vendor/onboarding', { method: 'PATCH', body, cookie: id })).status, 403);
  assert.equal((await f.send('vendor/onboarding', { method: 'PATCH', body: { verification_status: 'approved' },
    cookie: id, headers: { Origin: origin, 'X-ScrapMart-CSRF': '1' } })).status, 422);
  assert.equal((await f.send('vendor/onboarding', { method: 'GET' })).status, 401);
  assert.equal(f.calls.length, 0);
});

test('vendor enrollment requires browser session and exact backend 204', async () => {
  const f = fixture(async req => {
    assert.equal(req.url, backendOrigin + '/api/v1/auth/vendor/enroll');
    assert.equal(req.headers.get('authorization'), 'Bearer ' + access);
    assert.equal(req.headers.get('x-scrapmart-csrf'), '1');
    assert.equal(req.headers.get('origin'), origin);
    assert.deepEqual(await req.json(), { business_name: 'Test Shop', current_password: password });
    return new Response(null, { status: 204 });
  });
  const body = { business_name: 'Test Shop', current_password: password };
  const id = await seed(f);
  assert.equal((await f.send('vendor/enroll', { body, cookie: id })).status, 204);
  assert.equal(f.calls.length, 1);
  assert.ok(await f.store.lookup(id));
});

test('vendor enrollment rejects malformed fields before backend dispatch', async () => {
  const f = fixture(() => assert.fail('invalid request reached backend'));
  const id = await seed(f);
  assert.equal((await f.send('vendor/enroll', { cookie: id,
    body: { business_name: '', current_password: password, verification_status: 'approved' } })).status, 422);
  assert.equal(f.calls.length, 0);
});

test('vendor identity upload forwards private image bytes with bearer and no public storage key', async () => {
  const image = Uint8Array.from([255, 216, 255, 217]);
  const f = fixture(async req => {
    assert.equal(new URL(req.url).pathname, '/api/v1/auth/vendor/identity-document');
    assert.equal(new URL(req.url).searchParams.get('identification_type'), 'national_id');
    assert.equal(req.headers.get('authorization'), 'Bearer ' + access);
    assert.equal(req.headers.get('content-type'), 'image/jpeg');
    assert.equal(req.headers.get('x-scrapmart-csrf'), '1');
    assert.deepEqual(new Uint8Array(await req.arrayBuffer()), image);
    return json({ document_status: 'submitted' });
  });
  const id = await seed(f);
  const request = new Request(origin + '/api/auth/vendor/identity-document?identification_type=national_id', {
    method: 'POST', headers: {
      Origin: origin, 'X-ScrapMart-CSRF': '1', 'Content-Type': 'image/jpeg',
      Cookie: '__Host-scrapmart_session=' + id,
    }, body: image,
  });
  const result = await createBffHandlers({ store: f.store, backend: f.backend, browserOrigin: origin })(
    request, ['vendor', 'identity-document']);
  assert.equal(result.status, 200);
  assert.deepEqual(await result.json(), { submitted: true });
  assert.equal(f.calls.length, 1);
});

test('vendor identity upload rejects unsupported content and invalid type before dispatch', async () => {
  const f = fixture(() => assert.fail('Invalid upload reached backend'));
  const id = await seed(f);
  for (const [type, kind, status] of [
    ['application/pdf', 'national_id', 415],
    ['image/png', 'unlisted', 422],
  ]) {
    const req = new Request(origin + '/api/auth/vendor/identity-document?identification_type=' + kind, {
      method: 'POST',
      headers: { Origin: origin, 'X-ScrapMart-CSRF': '1', 'Content-Type': type,
        Cookie: '__Host-scrapmart_session=' + id },
      body: Uint8Array.of(1, 2, 3),
    });
    const result = await createBffHandlers({ store: f.store, backend: f.backend, browserOrigin: origin })(
      req, ['vendor', 'identity-document']);
    assert.equal(result.status, status);
  }
  assert.equal(f.calls.length, 0);
});

test('phone OTP requests use authenticated session and never expose SMS code', async () => {
  const f = fixture(async req => {
    assert.equal(req.url, backendOrigin + '/api/v1/auth/phone/send-code');
    assert.equal(req.headers.get('authorization'), 'Bearer ' + access);
    assert.equal(req.headers.get('x-scrapmart-csrf'), '1');
    assert.deepEqual(await req.json(), {});
    return json({ message: 'Request accepted.' }, 202);
  });
  const id = await seed(f);
  const reply = await f.send('phone/send-code', { cookie: id, body: {} });
  assert.equal(reply.status, 202);
  assert.ok(!(await reply.text()).includes('123456'));
  assert.equal(f.calls.length, 1);
});

test('phone OTP verification confirms only an exact backend 204', async () => {
  const f = fixture(async req => {
    assert.equal(req.url, backendOrigin + '/api/v1/auth/phone/verify-code');
    assert.equal(req.headers.get('authorization'), 'Bearer ' + access);
    assert.deepEqual(await req.json(), { code: '123456' });
    return new Response(null, { status: 204 });
  });
  const id = await seed(f);
  const reply = await f.send('phone/verify-code', { cookie: id, body: { code: '123456' } });
  assert.equal(reply.status, 204);
  assert.equal(f.calls.length, 1);
});

test('phone OTP verification rejects client-specified numbers and invalid codes', async () => {
  const f = fixture(() => assert.fail('invalid phone request dispatched'));
  const id = await seed(f);
  assert.equal((await f.send('phone/send-code', { cookie: id, body: { phone: '+2348000000000' } })).status, 422);
  assert.equal((await f.send('phone/verify-code', { cookie: id, body: { code: 'abcdef' } })).status, 422);
  assert.equal((await f.send('phone/verify-code', { cookie: id, body: { code: '123456', verified: true } })).status, 422);
  assert.equal((await f.send('phone/send-code', { body: {} })).status, 401);
  assert.equal(f.calls.length, 0);
});

test('vendor formally submits complete verification evidence without granting approval', async () => {
  const f = fixture(async req => {
    assert.equal(req.url, backendOrigin + '/api/v1/auth/vendor/verification/submit');
    assert.equal(req.headers.get('authorization'), 'Bearer ' + access);
    assert.equal(req.headers.get('origin'), origin);
    assert.equal(req.headers.get('x-scrapmart-csrf'), '1');
    assert.deepEqual(await req.json(), {});
    return Response.json({ verification_status: 'pending' }, { status: 200 });
  });
  const id = await seed(f);
  const reply = await f.send('vendor/verification/submit', { cookie: id, body: {} });
  assert.equal(reply.status, 200);
  assert.deepEqual(await reply.json(), { submitted_for_review: true });
  assert.equal(f.calls.length, 1);
});

test('verification review submission rejects client approval or arbitrary evidence metadata', async () => {
  const f = fixture(() => assert.fail('untrusted submission reached backend'));
  const id = await seed(f);
  assert.equal((await f.send('vendor/verification/submit', { cookie: id,
    body: { verification_status: 'approved' } })).status, 422);
  assert.equal((await f.send('vendor/verification/submit', { body: {} })).status, 401);
  assert.equal(f.calls.length, 0);
});
