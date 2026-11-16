import test from 'node:test';
import assert from 'node:assert/strict';
import { buyerLogoutDestination, createBuyerLogoutClient } from '../src/lib/buyer-logout.ts';

test('logout sends only a same-origin CSRF-protected POST and accepts exact confirmation', async () => {
  const calls = [];
  const logout = createBuyerLogoutClient(async (path, init) => {
    calls.push({ path, init });
    return new Response(null, { status: 204 });
  });
  const result = await logout();
  assert.equal(buyerLogoutDestination(result), '/login?role=buyer');
  assert.equal(calls.length, 1);
  assert.equal(calls[0].path, '/api/auth/logout');
  assert.deepEqual(calls[0].init, {
    method: 'POST', credentials: 'same-origin', cache: 'no-store', redirect: 'error',
    headers: { 'X-ScrapMart-CSRF': '1' },
  });
});

test('backend failure and unexpected success never claim confirmed logout or navigation', async () => {
  for (const response of [new Response(null, { status: 200 }), Response.json({ detail: { code: 'logout_unconfirmed' } }, { status: 503 })]) {
    const result = await createBuyerLogoutClient(async () => response)();
    assert.equal(result.status, 'error');
    assert.equal(buyerLogoutDestination(result), null);
    assert.match(result.message, /could not confirm sign-out/);
  }
  const offline = await createBuyerLogoutClient(async () => { throw Error('private upstream detail'); })();
  assert.equal(buyerLogoutDestination(offline), null);
  assert.doesNotMatch(offline.message, /private upstream detail/);
});

test('simultaneous logout attempts dispatch once', async () => {
  let resolve;
  let calls = 0;
  const logout = createBuyerLogoutClient(async () => {
    calls++;
    return new Promise(done => { resolve = done; });
  });
  const first = logout();
  assert.equal((await logout()).status, 'error');
  assert.equal(calls, 1);
  resolve(new Response(null, { status: 204 }));
  assert.equal(buyerLogoutDestination(await first), '/login?role=buyer');
});

test('already inactive session is verified before redirecting to Buyer login', async () => {
  const calls = [];
  const logout = createBuyerLogoutClient(async (path) => {
    calls.push(path);
    return Response.json({ detail: { code: 'session_required' } }, { status: 401 });
  });
  const result = await logout();
  assert.equal(result.status, 'already_signed_out');
  assert.equal(buyerLogoutDestination(result), '/login?role=buyer');
  assert.deepEqual(calls, ['/api/auth/logout', '/api/auth/session']);
});

test('failed verification and network failure retain Retry state without a success claim', async () => {
  for (const session of [Response.json({ authenticated: true }, { status: 200 }),
    Response.json({ detail: { code: 'session_refresh_required' } }, { status: 401 })]) {
    const result = await createBuyerLogoutClient(async path => path === '/api/auth/logout'
      ? Response.json({ detail: { code: 'session_required' } }, { status: 401 }) : session)();
    assert.equal(result.status, 'error'); assert.equal(buyerLogoutDestination(result), null);
    assert.match(result.message, /Retry/);
  }
  const result = await createBuyerLogoutClient(async () => { throw Error('private detail'); })();
  assert.equal(result.status, 'error'); assert.equal(buyerLogoutDestination(result), null);
  assert.match(result.message, /Retry/); assert.doesNotMatch(result.message, /private detail/);
});

test('Retry after an unconfirmed logout verifies the inactive browser session', async () => {
  let attempts = 0;
  const logout = createBuyerLogoutClient(async path => {
    if (path === '/api/auth/logout' && ++attempts === 1) {
      return Response.json({ detail: { code: 'logout_unconfirmed' } }, { status: 503 });
    }
    return Response.json({ detail: { code: 'session_required' } }, { status: 401 });
  });
  assert.equal((await logout()).status, 'error');
  const retried = await logout();
  assert.equal(retried.status, 'already_signed_out');
  assert.equal(buyerLogoutDestination(retried), '/login?role=buyer');
});
