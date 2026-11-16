import test from 'node:test';
import assert from 'node:assert/strict';
import { createVendorAuthClient } from '../src/lib/vendor-auth.ts';

const values = {
  fullName: 'Test Vendor',
  email: 'vendor@example.test',
  phone: '08012345678',
  password: 'Synthetic passphrase for tests',
  businessName: 'Test Scrap Shop',
  previewConsent: true,
};

test('vendor signup sends only registration fields to same-origin BFF', async () => {
  let calls = 0;
  const client = createVendorAuthClient(async (path, options) => {
    calls++;
    assert.equal(path, '/api/auth/vendor/signup');
    assert.equal(options.method, 'POST');
    assert.equal(options.credentials, 'same-origin');
    assert.equal(options.headers['X-ScrapMart-CSRF'], '1');
    assert.deepEqual(JSON.parse(options.body), {
      full_name: values.fullName,
      email: values.email,
      phone_number: values.phone,
      password: values.password,
      business_name: values.businessName,
    });
    return Response.json({ message: 'If registration was successful, you can now sign in.' }, { status: 202 });
  });
  assert.equal((await client.signup(values)).status, 'accepted');
  assert.equal(calls, 1);
});

test('vendor signup does not claim success on backend unavailable', async () => {
  const client = createVendorAuthClient(async () => Response.json({
    detail: { code: 'authentication_disabled', message: 'Authentication request could not be completed.' },
  }, { status: 503 }));
  const result = await client.signup(values);
  assert.equal(result.status, 'error');
  assert.match(result.message, /not activated/i);
});

test('vendor signup rejects invalid input without contacting backend', async () => {
  const client = createVendorAuthClient(async () => { throw Error('unexpected request'); });
  const result = await client.signup({ ...values, businessName: '' });
  assert.equal(result.status, 'error');
});
