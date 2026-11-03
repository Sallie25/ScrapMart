import test from 'node:test';
import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';
import { CredentialVault, SessionError, hashIdentifier, newIdentifier } from '../src/lib/server/sessions/crypto.ts';
import { SessionStore } from '../src/lib/server/sessions/store.ts';
import { browserSessionCookie, createLocalSessionStore } from '../src/lib/server/sessions/index.ts';

assert.notEqual(process.env.SCRAPMART_BFF_ISOLATED_TEST, '1', 'Offline tests must never run in real-driver mode');

const credentials = () => ({ accessToken: 'offline-test-access', refreshCookie: newIdentifier(), accessExpiresAt: new Date(Date.now() + 60000).toISOString() });
const vault = () => new CredentialVault('v1', { v1: randomBytes(32) });
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };

// Offline driver injection is restricted to the explicit test loader.
import { DatabaseDouble } from './helpers/session-pg-double.mjs';
async function fixture() {
  const db = new DatabaseDouble(); const store = new SessionStore(db.settings, vault()); const initial = credentials();
  const id = await store.create(initial, new Date(Date.now() + 120000));
  return { db, store, id, initial };
}

test('opaque identifiers are random, canonical and stored only as SHA-256 hashes', async () => {
  const { db, store, id } = await fixture();
  assert.equal(id.length, 43); assert.notEqual(newIdentifier(), id);
  assert.match(db.row.hash, /^[a-f0-9]{64}$/); assert.equal(db.row.hash, hashIdentifier(id));
  assert.ok(!JSON.stringify(db.calls).includes(id));
  assert.ok(await store.lookup(id)); assert.equal(await store.lookup(newIdentifier()), null);
  assert.throws(() => hashIdentifier('bad'), SessionError);
});
test('AES-GCM uses fresh nonces, hides credentials, authenticates ciphertext and row identity', () => {
  const v = vault(); const c = credentials(); const hash = hashIdentifier(newIdentifier());
  const a = v.seal(hash, c); const b = v.seal(hash, c);
  assert.notEqual(a.nonce, b.nonce); assert.notEqual(a.ciphertext, b.ciphertext);
  assert.ok(!JSON.stringify(a).includes(c.accessToken)); assert.ok(!JSON.stringify(a).includes(c.refreshCookie));
  assert.deepEqual(v.open(hash, a), c); assert.equal(JSON.stringify(v), '{}');
  assert.throws(() => v.open(hashIdentifier(newIdentifier()), a), SessionError);
  for (const field of ['nonce', 'ciphertext', 'tag']) {
    const bytes = Buffer.from(a[field], 'base64'); bytes[0] ^= 1;
    assert.throws(() => v.open(hash, { ...a, [field]: bytes.toString('base64') }), SessionError);
  }
});
test('key versions support retained old keys and reject unknown/removed/wrong keys', () => {
  const old = randomBytes(32), next = randomBytes(32), hash = hashIdentifier(newIdentifier());
  const a = new CredentialVault('old', { old }).seal(hash, credentials());
  const rotated = new CredentialVault('next', { old, next });
  assert.ok(rotated.open(hash, a)); assert.equal(rotated.seal(hash, credentials()).version, 'next');
  assert.throws(() => new CredentialVault('next', { next }).open(hash, a), SessionError);
  assert.throws(() => new CredentialVault('old', { old: randomBytes(32) }).open(hash, a), SessionError);
  assert.throws(() => new CredentialVault('missing', { old }), SessionError);
  assert.throws(() => new CredentialVault('old', { old: Buffer.alloc(8) }), SessionError);
});
test('expiration and revocation deny lookup, access and refresh; expired creation fails', async () => {
  const { db, store, id } = await fixture();
  db.row.expires_at = new Date(0);
  assert.equal(await store.lookup(id), null);
  await assert.rejects(store.withAccess(id, async () => assert.fail()), SessionError);
  await assert.rejects(store.refresh(id, async () => assert.fail()), SessionError);
  await assert.rejects(store.create(credentials(), new Date(0)), SessionError);
  db.row.expires_at = new Date(Date.now() + 10000);
  await store.revoke(id); await store.revoke(id);
  assert.equal(await store.lookup(id), null); assert.equal(db.row.envelope, null);
});
test('two store instances share a durable refresh claim; only one calls upstream', async () => {
  const { db, store, id, initial } = await fixture();
  // Shared vault is required across instances, just as configured keys are shared.
  const v = vault(); db.row.envelope = v.seal(db.row.hash, initial);
  const a = new SessionStore(db.settings, v), b = new SessionStore(db.settings, v);
  const entered = deferred(), release = deferred(); let calls = 0; const replacement = credentials();
  const first = a.refresh(id, async cookie => { assert.equal(cookie, initial.refreshCookie); calls++; entered.resolve(); await release.promise; return replacement; });
  await entered.promise;
  await assert.rejects(b.refresh(id, async () => { calls++; return credentials(); }), SessionError);
  assert.equal(await store.lookup(id), null);
  release.resolve(); const successor = await first; assert.equal(calls, 1);
  assert.equal(await a.lookup(id), null); assert.ok(await b.lookup(successor));
  const row = db.rows.find(row => row.hash === hashIdentifier(successor));
  assert.deepEqual(v.open(row.hash, row.envelope), replacement);
});
test('lost upstream response blocks all later refresh attempts without reuse', async () => {
  const { db, store, id } = await fixture(); let calls = 0;
  await assert.rejects(store.refresh(id, async () => { calls++; throw new Error('timeout with sensitive context'); }), SessionError);
  assert.equal(db.row.status, 'uncertain'); assert.equal(db.row.envelope, null);
  await assert.rejects(store.refresh(id, async () => { calls++; return credentials(); }), SessionError);
  assert.equal(calls, 1); assert.equal(await store.lookup(id), null);
});
test('identical replacement refresh credential is rejected', async () => {
  const { db, store, id, initial } = await fixture();
  await assert.rejects(store.refresh(id, async () => initial), SessionError);
  assert.equal(db.row.status, 'uncertain');
});
test('logout during refresh cannot be undone by the late replacement', async () => {
  const { db, store, id } = await fixture(); const entered = deferred(), release = deferred();
  const pending = store.refresh(id, async () => { entered.resolve(); await release.promise; return credentials(); });
  await entered.promise; await store.revoke(id); release.resolve();
  await assert.rejects(pending, SessionError);
  assert.equal(db.row.status, 'revoked'); assert.equal(db.row.envelope, null); assert.equal(await store.lookup(id), null);
});
test('storage outages fail closed and suppress sensitive driver errors', async () => {
  const { db, store, id } = await fixture(); db.outage = true;
  for (const operation of [() => store.lookup(id), () => store.revoke(id), () => store.create(credentials(), new Date(Date.now()+60000)),
    () => store.withAccess(id, async () => assert.fail()), () => store.refresh(id, async () => assert.fail())]) {
    await assert.rejects(operation(), e => e instanceof SessionError && !String(e).includes('sensitive'));
  }
});
test('lost claim acknowledgment never calls upstream and leaves session blocked', async () => {
  const { db, store, id } = await fixture(); db.loseClaim = true;
  await assert.rejects(store.refresh(id, async () => assert.fail()), SessionError);
  assert.equal(db.row.status, 'refreshing'); assert.equal(await store.lookup(id), null);
});
test('lost final commit acknowledgment retires the old browser identifier', async () => {
  const { db, store, id } = await fixture(); db.loseFinish = true;
  await assert.rejects(store.refresh(id, async () => credentials()), SessionError);
  assert.equal(db.row.status, 'retired'); assert.equal(await store.lookup(id), null); assert.equal(await store.lookup(id), null);
});
test('outage after sending refresh leaves durable claim blocked when quarantine fails', async () => {
  const { db, store, id } = await fixture();
  await assert.rejects(store.refresh(id, async () => { db.outage = true; return credentials(); }), SessionError);
  db.outage = false; assert.equal(db.row.status, 'refreshing'); assert.equal(await store.lookup(id), null);
});
test('access callback sees credentials only on server; public lookup excludes them', async () => {
  const { store, id, initial } = await fixture();
  assert.equal(await store.withAccess(id, async token => token === initial.accessToken), true);
  assert.deepEqual(Object.keys(await store.lookup(id)), ['expiresAt']);
});
test('sequential refresh uses only the committed replacement cookie', async () => {
  const { store, id, initial } = await fixture(); const replacement = credentials();
  const successor = await store.refresh(id, async cookie => { assert.equal(cookie, initial.refreshCookie); return replacement; });
  await store.refresh(successor, async cookie => { assert.equal(cookie, replacement.refreshCookie); assert.notEqual(cookie, initial.refreshCookie); return credentials(); });
});
test('expired access and session expiry during refresh deny credential use', async () => {
  const { db, store, id } = await fixture();
  const successor = await store.refresh(id, async () => ({ ...credentials(), accessExpiresAt: new Date(0).toISOString() }));
  await assert.rejects(store.withAccess(successor, async () => assert.fail()), SessionError);
  await assert.rejects(store.refresh(successor, async () => { db.rows.find(row => row.hash === hashIdentifier(successor)).expires_at = new Date(0); return credentials(); }), SessionError);
  assert.equal(await store.lookup(id), null);
});
test('corrupt encrypted record never dispatches upstream', async () => {
  const { db, store, id } = await fixture(); db.row.envelope.tag = Buffer.alloc(16).toString('base64');
  await assert.rejects(store.refresh(id, async () => assert.fail()), SessionError);
  assert.equal(db.row.status, 'uncertain');
});
test('configuration fails before pool creation and cookie policy is opaque/host-only', () => {
  assert.throws(() => createLocalSessionStore({}), SessionError);
  // Ephemeral test material only; no environment reads or database construction.
  const config = { BFF_SESSION_KEY_VERSION: 'v1', BFF_SESSION_KEYS_JSON: JSON.stringify({ v1: randomBytes(32).toString('base64') }),
    BFF_SESSION_DB_HOST: 'cloud.invalid', BFF_SESSION_DB_PORT: '55440', BFF_SESSION_DB_NAME: 'scrapmart_bff_local_test', BFF_SESSION_DB_USER: 'scrapmart_bff_runtime' };
  assert.throws(() => createLocalSessionStore(config), SessionError);
  assert.deepEqual(browserSessionCookie, { name: '__Host-scrapmart_session', httpOnly: true, secure: true, sameSite: 'lax', path: '/' });
  assert.equal('domain' in browserSessionCookie, false);
});

test('transaction-bound clients, pools and duck-typed query adapters are rejected without invocation', () => {
  let touched = false;
  class Client { query() { touched = true; } }
  for (const adapter of [new Client(), { query() { touched = true; } }, { connect() { touched = true; } },
    Object.assign(new DatabaseDouble().settings, { query() { touched = true; } })]) {
    assert.throws(() => new SessionStore(adapter, vault()), SessionError);
  }
  const settings = new DatabaseDouble().settings;
  Object.defineProperty(settings, 'password', { get() { touched = true; return 'unused'; } });
  assert.throws(() => new SessionStore(settings, vault()), SessionError);
  assert.equal(touched, false);
});

test('claim is acknowledged and its owned connection released before upstream dispatch', async () => {
  const { db, store, id } = await fixture();
  const successor = await store.refresh(id, async () => {
    assert.equal(db.row.status, 'refreshing');
    assert.ok(db.releases.length >= 2);
    assert.equal(db.calls.some(call => call.sql === 'BEGIN'), false);
    return credentials();
  });
  assert.notEqual(successor, id); assert.equal(await store.lookup(id), null);
  assert.ok(await store.lookup(successor));
  assert.deepEqual(db.calls.filter(call => ['BEGIN', 'COMMIT'].includes(call.sql)).map(call => call.sql), ['BEGIN', 'COMMIT']);
});

test('lost completion acknowledgment plus failed quarantine blocks the browser ID across instances', async () => {
  const { db, store, id } = await fixture(); db.loseFinish = true; db.failQuarantine = true;
  await assert.rejects(store.refresh(id, async () => credentials()), SessionError);
  assert.equal(db.row.status, 'retired'); assert.equal(db.row.envelope, null);
  assert.equal(db.rows.filter(row => row.status === 'active').length, 1); // Undisclosed orphan, not recovered.
  const restarted = new SessionStore(db.settings, vault());
  assert.equal(await restarted.lookup(id), null);
  await assert.rejects(restarted.withAccess(id, async () => assert.fail()), SessionError);
  await assert.rejects(restarted.refresh(id, async () => assert.fail()), SessionError);
  assert.ok(db.releases.includes(true));
});

test('failed completion commit rolls back retirement/insertion and preserves the claim when cleanup fails', async () => {
  const { db, store, id } = await fixture(); db.failCommitBefore = true; db.failQuarantine = true;
  await assert.rejects(store.refresh(id, async () => credentials()), SessionError);
  assert.equal(db.rows.length, 1); assert.equal(db.row.status, 'refreshing');
  assert.equal(await store.lookup(id), null);
  assert.ok(db.calls.some(call => call.sql === 'ROLLBACK')); assert.ok(db.releases.includes(true));
});

test('storage outage after committed completion and lost acknowledgment cannot reactivate the old ID on recovery', async () => {
  const { db, store, id } = await fixture();
  db.afterCommit = async () => { db.outage = true; }; db.loseFinish = true;
  await assert.rejects(store.refresh(id, async () => credentials()), SessionError);
  await assert.rejects(store.lookup(id), SessionError);
  db.outage = false;
  const freshInstance = new SessionStore(db.settings, vault());
  assert.equal(await freshInstance.lookup(id), null);
  await assert.rejects(freshInstance.refresh(id, async () => assert.fail()), SessionError);
  assert.equal(db.row.status, 'retired'); assert.ok(db.releases.includes(true));
});

test('insert failure cannot leave a retired parent without atomic completion', async () => {
  const { db, store, id } = await fixture(); db.failInsert = true;
  await assert.rejects(store.refresh(id, async () => credentials()), SessionError);
  assert.equal(db.rows.length, 1); assert.equal(db.row.status, 'uncertain');
});

test('logout through any retired identifier revokes current and future family access', async () => {
  const { db, store, id } = await fixture();
  const first = await store.refresh(id, async () => credentials());
  const second = await store.refresh(first, async () => credentials());
  assert.ok(await store.lookup(second));
  await store.revoke(first);
  for (const handle of [id, first, second]) {
    assert.equal(await store.lookup(handle), null);
    await assert.rejects(store.withAccess(handle, async () => assert.fail()), SessionError);
    await assert.rejects(store.refresh(handle, async () => assert.fail()), SessionError);
  }
  assert.equal(db.row.status, 'revoked');
});

test('logout after committed completion but before identifier handoff blocks the late result', async () => {
  const { db, store, id } = await fixture(); const entered = deferred(), release = deferred();
  db.afterCommit = async () => { entered.resolve(); await release.promise; };
  const pending = store.refresh(id, async () => credentials());
  await entered.promise; await store.revoke(id); release.resolve();
  const successor = await pending;
  assert.equal(await store.lookup(successor), null); assert.equal(db.row.status, 'revoked');
});

test('lost completion acknowledgment after logout cannot overwrite family revocation', async () => {
  const { db, store, id } = await fixture();
  db.afterCommit = async () => { await store.revoke(id); };
  db.loseFinish = true; db.failQuarantine = true;
  await assert.rejects(store.refresh(id, async () => credentials()), SessionError);
  assert.equal(db.row.status, 'revoked'); assert.equal(await store.lookup(id), null);
});

test('identifier rotation preserves absolute expiry and binds new encryption to the successor hash', async () => {
  const { db, store, id } = await fixture();
  const successor = await store.refresh(id, async () => credentials());
  const child = db.rows.find(row => row.hash === hashIdentifier(successor));
  assert.equal(child.root_hash, hashIdentifier(id)); assert.equal(child.expires_at, db.row.expires_at);
  assert.equal(db.row.status, 'retired'); assert.equal(db.row.envelope, null);
});

test('closed owned pools fail closed without dispatching upstream', async () => {
  const { store, id } = await fixture(); await store.close();
  await assert.rejects(store.lookup(id), SessionError);
  await assert.rejects(store.refresh(id, async () => assert.fail()), SessionError);
});
