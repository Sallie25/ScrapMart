import test from 'node:test';
import assert from 'node:assert/strict';
import { randomBytes, X509Certificate } from 'node:crypto';
import { rootCertificates } from 'node:tls';
import ConnectionParameters from 'pg/lib/connection-parameters';
import { AuthenticationRuntimeConfiguration, RuntimeConfigurationError } from '../src/lib/server/auth/configuration.ts';
import { OwnedSessionDatabase } from '../src/lib/server/sessions/database.ts';
import { createLocalSessionStore } from '../src/lib/server/sessions/index.ts';
import { DatabaseDouble, poolObservations } from './helpers/session-pg-double.mjs';
import { POST } from '../src/app/api/auth/[...operation]/route.ts';

assert.notEqual(process.env.SCRAPMART_BFF_ISOLATED_TEST, '1', 'Configuration tests must never use real PostgreSQL');
function fixture() {
  const db = new DatabaseDouble();
  const env = { BFF_AUTH_ENABLED: 'true', BFF_AUTH_ENVIRONMENT: 'staging',
    BFF_SESSION_DB_HOST: 'database.scrapmart.test', BFF_SESSION_DB_PORT: String(db.settings.port),
    BFF_SESSION_DB_NAME: 'scrapmart_bff_staging', BFF_SESSION_DB_USER: 'scrapmart_bff_runtime',
    BFF_SESSION_DB_PASSWORD: randomBytes(32).toString('base64url'),
    BFF_SESSION_KEY_VERSION: 'v1', BFF_SESSION_KEYS_JSON: JSON.stringify({ v1: randomBytes(32).toString('base64') }),
    BFF_BACKEND_ORIGIN: 'https://backend.scrapmart.test', BFF_BROWSER_ORIGIN: 'https://scrapmart.test' };
  return { db, env };
}
function invalid(env) {
  const before = poolObservations.length;
  assert.throws(() => new AuthenticationRuntimeConfiguration(env), error => {
    assert.ok(error instanceof RuntimeConfigurationError);
    assert.equal(error.message, 'Authentication runtime configuration is invalid');
    assert.equal(error.cause, undefined);
    if (env.BFF_SESSION_DB_PASSWORD) assert.ok(!JSON.stringify(error).includes(env.BFF_SESSION_DB_PASSWORD));
    return true;
  });
  assert.equal(poolObservations.length, before, 'Invalid startup must not construct a pool');
}

test('authentication defaults off without reading secrets or constructing dependencies', async () => {
  const before = poolObservations.length;
  for (const gate of [undefined, 'false']) {
    const env = { BFF_AUTH_ENABLED: gate };
    Object.defineProperty(env, 'BFF_SESSION_KEYS_JSON', { get() { assert.fail('Disabled runtime read secret'); } });
    const config = new AuthenticationRuntimeConfiguration(env);
    assert.equal(config.enabled, false);
    const runtime = config.createRuntime(() => assert.fail('Disabled runtime called transport'));
    const response = await runtime.handle(new Request('https://scrapmart.test/api/auth/session'), ['session']);
    assert.equal(response.status, 503);
    assert.equal((await response.json()).detail.code, 'authentication_disabled');
    await runtime.close();
  }
  assert.equal(poolObservations.length, before);
});

test('only the exact true gate permits complete startup validation', () => {
  for (const gate of ['', 'TRUE', '1', 'yes', ' true', 'false ', 'enabled']) invalid({ ...fixture().env, BFF_AUTH_ENABLED: gate });
});

test('each required runtime value is checked before any pool construction', () => {
  const { env } = fixture();
  for (const name of Object.keys(env).filter(name => name !== 'BFF_AUTH_ENABLED')) {
    const missing = { ...env }; delete missing[name]; invalid(missing);
    invalid({ ...env, [name]: '' });
    invalid({ ...env, [name]: ' ' + env[name] });
  }
});

test('database target, restricted role, password and environment fail closed', () => {
  const { env } = fixture();
  for (const host of ['localhost', '127.0.0.1', '127.1', '2130706433', '::1', '[::1]', '/tmp/postgres',
    'postgres://database.scrapmart.test', 'database.scrapmart.test/path', 'db', 'db.local',
    'db.internal', 'db.localhost', 'DB.scrapmart.test', 'db.scrapmart.test.', '-db.scrapmart.test']) {
    invalid({ ...env, BFF_SESSION_DB_HOST: host });
  }
  for (const port of ['0', '543', '65536', '05432', '5e3', '+5432', '5432.0', '5432 ']) invalid({ ...env, BFF_SESSION_DB_PORT: port });
  for (const name of ['postgres', 'scrapmart_bff_local_test', 'scrapmart_bff_production', 'scrapmart_bff_staging?sslmode=disable']) invalid({ ...env, BFF_SESSION_DB_NAME: name });
  for (const user of ['postgres', 'owner', 'scrapmart_bff_runtime@host']) invalid({ ...env, BFF_SESSION_DB_USER: user });
  for (const value of ['short', 'x'.repeat(1025), 'x'.repeat(24) + '\0', 'x'.repeat(24) + '\n', 'x'.repeat(24) + ' ']) invalid({ ...env, BFF_SESSION_DB_PASSWORD: value });
  invalid({ ...env, BFF_AUTH_ENVIRONMENT: 'development' });
  invalid({ ...env, NODE_TLS_REJECT_UNAUTHORIZED: '0' });
});

test('backend and browser origins require distinct canonical HTTPS DNS origins', () => {
  const { env } = fixture();
  for (const name of ['BFF_BACKEND_ORIGIN', 'BFF_BROWSER_ORIGIN']) {
    for (const url of ['http://backend.scrapmart.test', 'https://localhost', 'https://127.0.0.1',
      'https://backend.scrapmart.test/', 'https://backend.scrapmart.test/api/v1/auth',
      'https://user:password@backend.scrapmart.test', 'https://backend.scrapmart.test?key=synthetic',
      'https://backend.scrapmart.test#fragment', 'https://backend.scrapmart.test:444', 'not-a-url']) {
      invalid({ ...env, [name]: url });
    }
  }
  invalid({ ...env, BFF_BACKEND_ORIGIN: env.BFF_BROWSER_ORIGIN });
});

test('key rings require canonical independent strong keys and a current version', () => {
  const { env } = fixture();
  const good = randomBytes(32).toString('base64');
  for (const value of ['{', 'null', '[]', '{}', JSON.stringify({ v1: 123 }),
    JSON.stringify({ v1: 'not-base64' }), JSON.stringify({ v1: good.slice(0, -1) }),
    JSON.stringify({ v1: Buffer.alloc(32).toString('base64') }),
    JSON.stringify({ v1: randomBytes(31).toString('base64') }),
    JSON.stringify({ v1: good, v2: good }),
    JSON.stringify({ bad_version: good }),
    JSON.stringify(Object.fromEntries(Array.from({ length: 9 }, (_, i) => ['v' + i, randomBytes(32).toString('base64')]))),
    ' '.repeat(8193)]) invalid({ ...env, BFF_SESSION_KEYS_JSON: value });
  for (const version of ['missing', 'v'.repeat(33), '../v1']) invalid({ ...env, BFF_SESSION_KEY_VERSION: version });
});

test('invalid CA material or private key input cannot reach pool construction', () => {
  const { env } = fixture();
  for (const ca of ['', 'invalid', '-----BEGIN PRIVATE KEY-----\nsynthetic\n-----END PRIVATE KEY-----',
    '-----BEGIN CERTIFICATE-----\nnot-a-certificate\n-----END CERTIFICATE-----', 'x'.repeat(65537)]) {
    invalid({ ...env, BFF_SESSION_DB_CA_PEM: ca });
  }
});

test('validated staging and production use strict TLS options without connecting or querying', async () => {
  for (const environment of ['staging', 'production']) {
    const { db, env } = fixture();
    const config = new AuthenticationRuntimeConfiguration({ ...env, BFF_AUTH_ENVIRONMENT: environment, BFF_SESSION_DB_NAME: 'scrapmart_bff_' + environment });
    assert.equal(config.enabled, true); assert.equal(JSON.stringify(config), '{}');
    assert.equal(db.connects, 0);
    assert.throws(() => config.createRuntime(), RuntimeConfigurationError);
    const runtime = config.createRuntime(() => assert.fail('No backend calls authorized'));
    const settings = poolObservations.at(-1);
    assert.deepEqual(settings.ssl, { rejectUnauthorized: true, minVersion: 'TLSv1.2', servername: env.BFF_SESSION_DB_HOST });
    assert.equal(settings.host, env.BFF_SESSION_DB_HOST);
    assert.equal(settings.database, 'scrapmart_bff_' + environment);
    assert.equal(settings.user, 'scrapmart_bff_runtime'); assert.equal(settings.password, env.BFF_SESSION_DB_PASSWORD);
    assert.equal(settings.max, 4); assert.equal(settings.connectionTimeoutMillis, 2000);
    assert.ok(settings.options.includes('synchronous_commit=on'));
    assert.ok(settings.options.includes('search_path=pg_catalog,bff_sessions,pg_temp'));
    assert.equal(db.connects, 0); assert.equal(db.calls.length, 0);
    const denied = await runtime.handle(new Request(env.BFF_BROWSER_ORIGIN + '/api/auth/logout', { method: 'POST' }), ['logout']);
    assert.equal(denied.status, 403); assert.equal(db.connects, 0);
    await runtime.close(); assert.equal(db.connects, 0);
  }
});

test('adapter rejects injected TLS overrides, identity changes, query adapters and accessors', () => {
  const { env } = fixture();
  const settings = { mode: 'tls', environment: 'staging', host: env.BFF_SESSION_DB_HOST,
    port: Number(env.BFF_SESSION_DB_PORT), database: env.BFF_SESSION_DB_NAME,
    user: env.BFF_SESSION_DB_USER, password: env.BFF_SESSION_DB_PASSWORD };
  for (const change of [{ ssl: false }, { ssl: { rejectUnauthorized: false } }, { connectionString: 'ignored' },
    { mode: 'local' }, { database: 'postgres' }, { user: 'postgres' }, { host: 'localhost' },
    { ca: 'invalid' }, { options: '-c synchronous_commit=off' }]) {
    const before = poolObservations.length;
    assert.throws(() => new OwnedSessionDatabase({ ...settings, ...change }), { message: 'Session operation unavailable' });
    assert.equal(poolObservations.length, before);
  }
  const getter = { ...settings };
  Object.defineProperty(getter, 'mode', { get() { assert.fail('Accessor invoked'); } });
  assert.throws(() => new OwnedSessionDatabase(getter), { message: 'Session operation unavailable' });
});

test('loopback disposable configuration remains isolated and uses its original no-TLS path', async () => {
  const { db, env } = fixture();
  const local = createLocalSessionStore({ ...env, BFF_SESSION_DB_HOST: db.settings.host,
    BFF_SESSION_DB_NAME: db.settings.database, BFF_SESSION_DB_PASSWORD: db.settings.password });
  assert.equal(poolObservations.at(-1).ssl, false);
  assert.equal(db.connects, 0); await local.close();
});

test('deployed route remains disabled even when a complete explicit runtime configuration exists', async () => {
  const { env } = fixture(); const before = poolObservations.length;
  const old = Object.fromEntries(Object.keys(env).map(name => [name, process.env[name]]));
  const fetch = globalThis.fetch;
  try {
    Object.assign(process.env, env);
    globalThis.fetch = () => assert.fail('No live network permitted');
    const response = await POST(new Request(env.BFF_BROWSER_ORIGIN + '/api/auth/buyer/login', { method: 'POST' }),
      { params: Promise.resolve({ operation: ['buyer', 'login'] }) });
    assert.equal(response.status, 503); assert.equal((await response.json()).detail.code, 'authentication_disabled');
    assert.equal(poolObservations.length, before);
  } finally {
    globalThis.fetch = fetch;
    for (const [name, value] of Object.entries(old)) { if (value === undefined) delete process.env[name]; else process.env[name] = value; }
  }
});


test('a valid public CA bundle is passed intact without changing verification policy', async () => {
  const { db, env } = fixture();
  const ca = rootCertificates.find(pem => {
    const cert = new X509Certificate(pem);
    return cert.ca && Date.parse(cert.validFrom) <= Date.now() && Date.parse(cert.validTo) > Date.now();
  });
  assert.ok(ca, 'Node must supply a currently valid public CA');
  const config = new AuthenticationRuntimeConfiguration({ ...env, BFF_SESSION_DB_CA_PEM: ca });
  const runtime = config.createRuntime(() => assert.fail('No transport calls authorized'));
  const ssl = poolObservations.at(-1).ssl;
  assert.equal(ssl.ca, ca); assert.equal(ssl.rejectUnauthorized, true);
  assert.equal(ssl.servername, env.BFF_SESSION_DB_HOST); assert.equal(ssl.minVersion, 'TLSv1.2');
  assert.equal('checkServerIdentity' in ssl, false, 'Use Node hostname verification');
  assert.equal(db.connects, 0); assert.equal(db.calls.length, 0); await runtime.close();
});

test('pg environment defaults cannot replace explicit database identity or disable TLS', async () => {
  const { db, env } = fixture();
  const overrides = { PGHOST: 'localhost', PGPORT: '1', PGDATABASE: 'postgres', PGUSER: 'postgres',
    PGPASSWORD: 'synthetic-unused', PGSSLMODE: 'no-verify', PGOPTIONS: '-c synchronous_commit=off',
    DATABASE_URL: 'postgresql://unused.invalid/unused' };
  const saved = Object.fromEntries(Object.keys(overrides).map(name => [name, process.env[name]]));
  let runtime;
  try {
    Object.assign(process.env, overrides);
    runtime = new AuthenticationRuntimeConfiguration(env).createRuntime(() => assert.fail());
    // pg's pure option parser only: no client, pool, socket, DNS or query.
    const effective = new ConnectionParameters(poolObservations.at(-1));
    assert.equal(effective.host, env.BFF_SESSION_DB_HOST);
    assert.equal(effective.port, Number(env.BFF_SESSION_DB_PORT));
    assert.equal(effective.database, env.BFF_SESSION_DB_NAME);
    assert.equal(effective.user, env.BFF_SESSION_DB_USER);
    assert.equal(effective.password, env.BFF_SESSION_DB_PASSWORD);
    assert.equal(effective.ssl.rejectUnauthorized, true);
    assert.equal(effective.ssl.servername, env.BFF_SESSION_DB_HOST);
    assert.equal(effective.ssl.minVersion, 'TLSv1.2');
    assert.ok(effective.options.includes('synchronous_commit=on'));
    assert.equal(db.connects, 0); assert.equal(db.calls.length, 0);
  } finally {
    if (runtime) await runtime.close();
    for (const [name, value] of Object.entries(saved)) {
      if (value === undefined) delete process.env[name]; else process.env[name] = value;
    }
  }
});

test('changing process-wide TLS policy after validation prevents pool creation', () => {
  const { env } = fixture(); const config = new AuthenticationRuntimeConfiguration(env);
  const before = poolObservations.length;
  const old = process.env.NODE_TLS_REJECT_UNAUTHORIZED;
  try {
    process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';
    assert.throws(() => config.createRuntime(() => assert.fail()), RuntimeConfigurationError);
    assert.equal(poolObservations.length, before);
  } finally {
    if (old === undefined) delete process.env.NODE_TLS_REJECT_UNAUTHORIZED;
    else process.env.NODE_TLS_REJECT_UNAUTHORIZED = old;
  }
});

test('expired and not-yet-valid CAs are rejected using their real X509 validity dates', () => {
  const { env } = fixture();
  const ca = rootCertificates.find(pem => new X509Certificate(pem).ca);
  assert.ok(ca);
  const cert = new X509Certificate(ca); const now = Date.now;
  try {
    Date.now = () => Date.parse(cert.validFrom) - 1;
    invalid({ ...env, BFF_SESSION_DB_CA_PEM: ca });
    Date.now = () => Date.parse(cert.validTo) + 1;
    invalid({ ...env, BFF_SESSION_DB_CA_PEM: ca });
  } finally { Date.now = now; }
});

test('prepared runtime uses a validated configuration snapshot and synthetic transport only', async () => {
  const { db, env } = fixture();
  env.BFF_SESSION_KEYS_JSON = JSON.stringify({ v1: randomBytes(32).toString('base64'), v2: randomBytes(32).toString('base64') });
  env.BFF_SESSION_KEY_VERSION = 'v2';
  const config = new AuthenticationRuntimeConfiguration(env);
  env.BFF_BACKEND_ORIGIN = 'https://changed.invalid';
  env.BFF_SESSION_DB_HOST = 'localhost';
  let calls = 0;
  const runtime = config.createRuntime(async req => {
    calls++;
    assert.equal(req.url, 'https://backend.scrapmart.test/api/v1/auth/vendor/signup');
    assert.equal(req.headers.get('origin'), 'https://scrapmart.test');
    assert.equal(req.headers.get('x-scrapmart-csrf'), '1');
    assert.equal(req.headers.has('cookie'), false);
    assert.equal(req.headers.has('authorization'), false);
    return Response.json({ message: 'If registration was successful, you can now sign in.' }, { status: 202 });
  });
  try {
    const result = await runtime.handle(new Request('https://scrapmart.test/api/auth/vendor/signup', {
      method: 'POST', headers: { Origin: 'https://scrapmart.test', 'X-ScrapMart-CSRF': '1', 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'synthetic@example.test', password: 'Synthetic password only', full_name: 'Synthetic Owner', business_name: 'Synthetic Shop' }),
    }), ['vendor', 'signup']);
    assert.equal(result.status, 202); assert.equal(result.headers.has('set-cookie'), false);
    assert.equal(calls, 1); assert.equal(db.connects, 0); assert.equal(db.calls.length, 0);
    assert.equal(poolObservations.at(-1).host, 'database.scrapmart.test');
  } finally { await runtime.close(); }
});
