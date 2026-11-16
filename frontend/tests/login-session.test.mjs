import test from 'node:test';
import assert from 'node:assert/strict';
import { createLoginSessionClient } from '../src/lib/login-session.ts';
import { createBuyerAuthClient } from '../src/lib/buyer-auth.ts';
import { createVendorAuthClient } from '../src/lib/vendor-auth.ts';

const session = (buyer, vendor) => Response.json({ authenticated: true,
  capabilities: { buyer, vendor, vendor_verification_status: vendor ? 'pending' : null },
  expires_at: new Date(Date.now() + 60000).toISOString() });

test('existing session detection uses backend capabilities for the actual account role', async () => {
  for (const [buyer, vendor, requested, actual] of [[true, false, 'vendor', 'buyer'],
    [false, true, 'buyer', 'vendor']]) {
    const client = createLoginSessionClient(async (path, init) => {
      assert.equal(path, '/api/auth/session');
      assert.deepEqual(init, { method: 'GET', credentials: 'same-origin', cache: 'no-store', redirect: 'error' });
      return session(buyer, vendor);
    });
    assert.deepEqual(await client.check(requested), { status: 'authenticated', role: actual });
  }
});

test('session lookup distinguishes anonymous, expired access and temporary failure', async () => {
  for (const [reply, expected] of [
    [Response.json({ detail: { code: 'session_required' } }, { status: 401 }), 'anonymous'],
    [Response.json({ detail: { code: 'session_refresh_required' } }, { status: 401 }), 'refresh_required'],
    [Response.json({ detail: { code: 'session_unavailable' } }, { status: 503 }), 'unavailable'],
    [Response.json({ detail: { code: 'unexpected' } }, { status: 401 }), 'unavailable'],
  ]) {
    const client = createLoginSessionClient(async () => reply);
    assert.equal((await client.check('buyer')).status, expected);
  }
});

test('expired access triggers one CSRF-protected refresh then rechecks actual role', async () => {
  const calls = []; let renewed = false;
  const client = createLoginSessionClient(async (path, init) => {
    calls.push({ path, init });
    if (path === '/api/auth/refresh') { renewed = true; return Response.json({ authenticated: true }); }
    return renewed ? session(false, true) : Response.json({ detail: { code: 'session_refresh_required' } }, { status: 401 });
  });
  assert.deepEqual(await client.resolve('buyer'), { status: 'authenticated', role: 'vendor' });
  assert.deepEqual(calls.map(call => call.path), ['/api/auth/session', '/api/auth/refresh', '/api/auth/session']);
  assert.deepEqual(calls[1].init, { method: 'POST', credentials: 'same-origin', cache: 'no-store',
    redirect: 'error', headers: { 'X-ScrapMart-CSRF': '1' } });
});

test('failed refresh cannot become a confirmed anonymous or authenticated session', async () => {
  for (const failure of [Response.json({ detail: { code: 'backend_unavailable' } }, { status: 503 }),
    Response.json({ detail: { code: 'session_required' } }, { status: 401 })]) {
    let checks = 0;
    const client = createLoginSessionClient(async path => {
      if (path === '/api/auth/refresh') return failure;
      checks++;
      return Response.json({ detail: { code: 'session_refresh_required' } }, { status: 401 });
    });
    assert.equal((await client.resolve('buyer')).status, 'unavailable');
    assert.ok(checks <= 2);
  }
});

test('both login clients identify logout_required without trusting a requested role', async () => {
  const reply = async () => Response.json({ detail: { code: 'logout_required' } }, { status: 409 });
  const credentials = { email: 'test@example.com', password: 'test password' };
  for (const client of [createBuyerAuthClient(reply), createVendorAuthClient(reply)]) {
    const result = await client.login(credentials);
    assert.equal(result.code, 'logout_required');
    assert.equal(result.message, "You're already signed in.");
  }
});

test('confirmed logout refreshes session state and permits account switching', async () => {
  const calls = [];
  let signedIn = true;
  const client = createLoginSessionClient(async (path, init) => {
    calls.push({ path, init });
    if (path === '/api/auth/logout') {
      assert.equal(init.method, 'POST');
      assert.equal(init.credentials, 'same-origin');
      assert.equal(init.headers['X-ScrapMart-CSRF'], '1');
      assert.equal(init.body, undefined);
      signedIn = false;
      return new Response(null, { status: 204 });
    }
    return signedIn ? session(false, true) : Response.json({ detail: { code: 'session_required' } }, { status: 401 });
  });
  assert.deepEqual(await client.check('buyer'), { status: 'authenticated', role: 'vendor' });
  assert.deepEqual(await client.switchAccount('vendor'), { status: 'signed_out' });
  assert.deepEqual(await client.check('buyer'), { status: 'anonymous' });
  assert.deepEqual(calls.map(call => call.path), ['/api/auth/session', '/api/auth/logout', '/api/auth/session', '/api/auth/session']);
});

test('failed or unconfirmed logout keeps the existing account and reports an error', async () => {
  for (const failure of [Response.json({ detail: { code: 'logout_unconfirmed' } }, { status: 503 }),
    new Response(null, { status: 200 })]) {
    let checks = 0;
    const client = createLoginSessionClient(async path => {
      if (path === '/api/auth/session') { checks++; return session(true, false); }
      return failure;
    });
    assert.deepEqual(await client.check('buyer'), { status: 'authenticated', role: 'buyer' });
    const result = await client.switchAccount('buyer');
    assert.equal(result.status, 'error');
    assert.match(result.message, /could not confirm sign-out/);
    assert.equal(checks, 1);
  }
});

test('account switching proceeds only after an already inactive session is verified', async () => {
  const calls = [];
  const client = createLoginSessionClient(async path => {
    calls.push(path);
    return Response.json({ detail: { code: 'session_required' } }, { status: 401 });
  });
  assert.deepEqual(await client.switchAccount('buyer'), { status: 'signed_out' });
  assert.deepEqual(calls, ['/api/auth/logout', '/api/auth/session', '/api/auth/session']);
});

test('overlapping mount checks share one controlled refresh and later checks run afresh', async () => {
  let checks = 0; let refreshes = 0; let release;
  const gate = new Promise(resolve => { release = resolve; });
  const client = createLoginSessionClient(async path => {
    if (path === '/api/auth/refresh') { refreshes++; await gate; return Response.json({ authenticated: true }); }
    checks++;
    return refreshes ? session(false, true) : Response.json({ detail: { code: 'session_refresh_required' } }, { status: 401 });
  });
  const first = client.resolve('buyer');
  const second = client.resolve('buyer');
  release();
  assert.deepEqual(await first, { status: 'authenticated', role: 'vendor' });
  assert.deepEqual(await second, { status: 'authenticated', role: 'vendor' });
  assert.equal(refreshes, 1); assert.equal(checks, 2);
  await client.resolve('vendor');
  assert.equal(checks, 3);
});

test('invalid refresh permits login only after the cleared session is rechecked', async () => {
  for (const role of ['buyer', 'vendor']) {
    let checks = 0; let refreshes = 0;
    const client = createLoginSessionClient(async path => {
      if (path === '/api/auth/refresh') { refreshes++; return Response.json({ detail: { code: 'session_required' } }, { status: 401 }); }
      checks++;
      return Response.json({ detail: { code: checks === 1 ? 'session_refresh_required' : 'session_required' } }, { status: 401 });
    });
    assert.deepEqual(await client.resolve(role), { status: 'anonymous' });
    assert.equal(refreshes, 1); assert.equal(checks, 2);
  }
});

test('a still-expired session after a successful refresh stops without looping', async () => {
  let refreshes = 0;
  const client = createLoginSessionClient(async path => {
    if (path === '/api/auth/refresh') { refreshes++; return Response.json({ authenticated: true }); }
    return Response.json({ detail: { code: 'session_refresh_required' } }, { status: 401 });
  });
  assert.deepEqual(await client.resolve('buyer'), { status: 'unavailable' });
  assert.equal(refreshes, 1);
});
