import test from 'node:test';
import assert from 'node:assert/strict';
import { buyerLoginDestination, createBuyerAuthClient } from '../src/lib/buyer-auth.ts';
const signup = { fullName: 'Ada Buyer', phone: '08012345678', email: 'ada@example.test', password: '  a long password  ', previewConsent: true };
const login = { email: 'ada@example.test', password: 'old password' };
const ack = 'If registration was successful, you can now sign in.';
const responder = (payload, status = 200) => Response.json(payload, { status });

test('signup sends only BFF fields, with the password unchanged and no stored credentials', async () => {
  const calls = [];
  const client = createBuyerAuthClient(async (path, init) => { calls.push({ path, init }); return responder({ message: ack }, 202); });
  assert.deepEqual(await client.signup(signup), { status: 'accepted', message: ack });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].path, '/api/auth/buyer/signup');
  assert.equal(calls[0].init.method, 'POST');
  assert.equal(calls[0].init.credentials, 'same-origin');
  assert.equal(calls[0].init.headers['X-ScrapMart-CSRF'], '1');
  assert.deepEqual(JSON.parse(calls[0].init.body), { full_name: signup.fullName, phone_number: signup.phone, email: signup.email, password: signup.password });
  assert.ok(!calls[0].init.body.includes('previewConsent'));
});

test('duplicate email receives neutral signup acknowledgment, never a false duplicate claim', async () => {
  const client = createBuyerAuthClient(async () => responder({ message: ack }, 202));
  assert.equal((await client.signup(signup)).message, ack);
  assert.equal((await client.signup(signup)).message, ack);
});

test('login navigates only for exact confirmed BFF success', async () => {
  const cases = [[responder({ authenticated: true }), '/buyer/dashboard'], [responder({ authenticated: false }), null],
    [responder({}), null], [responder({ authenticated: true }, 202), null],
    [responder({ detail: { code: 'invalid_credentials' } }, 401), null]];
  for (const [response, destination] of cases) {
    const client = createBuyerAuthClient(async (path, init) => {
      assert.equal(path, '/api/auth/buyer/login');
      assert.deepEqual(JSON.parse(init.body), login);
      return response;
    });
    assert.equal(buyerLoginDestination(await client.login(login)), destination);
  }
});

test('failed, disabled and validation responses show safe messages and fields', async () => {
  for (const [code, status, fragment] of [['authentication_disabled', 503, 'not activated'], ['invalid_credentials', 401, 'incorrect'],
    ['validation_error', 422, 'highlighted'], ['backend_unavailable', 503, 'not available'], ['rate_limited', 429, 'Too many']]) {
    const client = createBuyerAuthClient(async () => responder({ detail: { code, message: 'secret upstream text', fields: ['email', 'private_token'] } }, status));
    const result = await client.login(login);
    assert.equal(result.status, 'error');
    assert.equal(buyerLoginDestination(result), null);
    assert.match(result.message, new RegExp(fragment));
    assert.doesNotMatch(result.message, /secret upstream/);
    if (code === 'validation_error') assert.deepEqual(result.fields, ['email']);
  }
  assert.equal((await createBuyerAuthClient(async () => { throw new Error('offline'); }).login(login)).status, 'error');
});

test('simultaneous submissions dispatch only once', async () => {
  let resolve;
  let calls = 0;
  const client = createBuyerAuthClient(async () => { calls++; return new Promise(done => { resolve = done; }); });
  const first = client.login(login);
  const second = await client.login(login);
  assert.equal(second.status, 'error');
  assert.equal(calls, 1);
  resolve(responder({ authenticated: true }));
  assert.equal(buyerLoginDestination(await first), '/buyer/dashboard');
});
