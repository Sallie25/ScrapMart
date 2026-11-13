import test from 'node:test';
import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';
import { createAuthenticationBootstrap } from '../src/lib/server/auth/runtime.ts';
import { buyerSessionDecision } from '../src/lib/server/auth/buyer-session.ts';
import { DatabaseDouble, poolObservations } from './helpers/session-pg-double.mjs';

const origin = 'https://scrapmart.test';
const fixture = () => {
  const db = new DatabaseDouble();
  const env = { BFF_AUTH_ENABLED: 'true', BFF_AUTH_ENVIRONMENT: 'staging',
    BFF_SESSION_DB_HOST: 'database.scrapmart.test', BFF_SESSION_DB_PORT: String(db.settings.port),
    BFF_SESSION_DB_NAME: 'scrapmart_bff_staging', BFF_SESSION_DB_USER: 'scrapmart_bff_runtime',
    BFF_SESSION_DB_PASSWORD: randomBytes(32).toString('base64url'),
    BFF_SESSION_KEY_VERSION: 'v1', BFF_SESSION_KEYS_JSON: JSON.stringify({ v1: randomBytes(32).toString('base64') }),
    BFF_BACKEND_ORIGIN: 'https://backend.scrapmart.test', BFF_BROWSER_ORIGIN: origin };
  return { db, env };
};
const response = (code, status) => Response.json({ detail: { code } }, { status });

test('disabled bootstrap reads no secrets, constructs no pool and cannot call transport', async () => {
  const before = poolObservations.length;
  const env = { BFF_AUTH_ENABLED: 'false' };
  Object.defineProperty(env, 'BFF_SESSION_KEYS_JSON', { get() { assert.fail('Read disabled secret'); } });
  const runtime = createAuthenticationBootstrap(env, () => assert.fail('Disabled transport used'));
  assert.equal(runtime.enabled, false);
  const result = await runtime.handle(new Request(origin + '/api/auth/session'), ['session']);
  assert.equal(result.status, 503);
  assert.equal((await result.json()).detail.code, 'authentication_disabled');
  assert.equal(poolObservations.length, before);
  await runtime.close(); await runtime.close();
});

test('invalid enabled configuration fails before pool construction', () => {
  const before = poolObservations.length;
  const { env } = fixture();
  delete env.BFF_SESSION_DB_PASSWORD;
  assert.throws(() => createAuthenticationBootstrap(env, () => assert.fail('Invalid transport used')));
  assert.equal(poolObservations.length, before);
});

test('valid enabled bootstrap injects backend transport, owns one lazy pool and closes it', async () => {
  const { db, env } = fixture();
  const before = poolObservations.length;
  let request;
  const runtime = createAuthenticationBootstrap(env, async input => {
    request = input;
    return Response.json({ message: 'If registration was successful, you can now sign in.' }, { status: 202 });
  });
  assert.equal(runtime.enabled, true);
  assert.equal(poolObservations.length, before + 1);
  assert.equal(db.connects, 0);
  const result = await runtime.handle(new Request(origin + '/api/auth/buyer/signup', { method: 'POST', headers: {
    Origin: origin, 'X-ScrapMart-CSRF': '1', 'Content-Type': 'application/json',
  }, body: JSON.stringify({ email: 'buyer@example.test', password: 'long synthetic password', full_name: 'Ada Buyer', phone_number: '08012345678' }) }), ['buyer', 'signup']);
  assert.equal(result.status, 202);
  assert.equal(new URL(request.url).pathname, '/api/v1/auth/buyer/signup');
  assert.equal(request.credentials, 'omit');
  assert.equal(db.connects, 0);
  await runtime.close(); await runtime.close();
  assert.equal(db.connects, 0);
  const closed = await runtime.handle(new Request(origin + '/api/auth/session'), ['session']);
  assert.equal(closed.status, 503);
});

test('Buyer guard requires a live Buyer capability and a future expiry', async () => {
  let calls = 0;
  const allowed = async request => {
    calls++; assert.equal(request.headers.get('cookie'), '__Host-scrapmart_session=synthetic');
    return Response.json({ authenticated: true, capabilities: { buyer: true, vendor: false, vendor_verification_status: null }, expires_at: new Date(Date.now() + 60000).toISOString() });
  };
  assert.equal(await buyerSessionDecision(null, allowed), 'login');
  assert.equal(calls, 0);
  assert.equal(await buyerSessionDecision('__Host-scrapmart_session=synthetic', allowed), 'allow');
  for (const body of [{ authenticated: false, capabilities: { buyer: true }, expires_at: new Date(Date.now() + 60000).toISOString() },
    { authenticated: true, capabilities: { buyer: false }, expires_at: new Date(Date.now() + 60000).toISOString() },
    { authenticated: true, capabilities: { buyer: true }, expires_at: new Date(0).toISOString() }]) {
    assert.equal(await buyerSessionDecision('cookie', async () => Response.json(body)), 'login');
  }
  assert.equal(await buyerSessionDecision('cookie', async () => response('session_required', 401)), 'login');
  assert.equal(await buyerSessionDecision('cookie', async () => response('session_refresh_required', 401)), 'refresh');
  assert.equal(await buyerSessionDecision('cookie', async () => response('authentication_disabled', 503)), 'unavailable');
  assert.equal(await buyerSessionDecision('cookie', async () => { throw new Error('offline'); }), 'unavailable');
});
