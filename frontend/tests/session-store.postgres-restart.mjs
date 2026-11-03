import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { guard, pool, identity, session, sessions, CredentialVault, key, credentials, expiry, hashIdentifier, SessionError } from './helpers/postgres-fixture.mjs';
import { faults, resetFaults } from './helpers/postgres-pg-faults.mjs';

await guard();
const db = pool(); await identity(db, 'scrapmart_bff_runtime');
const path = '/tmp/bff/restart-state.json';
try {
  if (process.argv[2] === 'prepare') {
    const secret = key(); const store = session(new CredentialVault('v1', { v1: secret }));
    const activeRoot = await store.create(credentials(), expiry());
    const active = await store.refresh(activeRoot, async () => credentials());
    const revoked = await store.create(credentials(), expiry()); await store.revoke(revoked);
    const uncertain = await store.create(credentials(), expiry());
    await assert.rejects(store.refresh(uncertain, async () => { throw new Error('synthetic loss'); }), SessionError);
    const fenced = await store.create(credentials(), expiry());
    faults.loseClaim = true;
    await assert.rejects(store.refresh(fenced, async () => assert.fail()), SessionError);
    const ambiguous = await store.create(credentials(), expiry());
    faults.loseCommit = true; faults.failQuarantine = true;
    await assert.rejects(store.refresh(ambiguous, async () => credentials()), SessionError);
    resetFaults();
    const before = (await db.query('SELECT pg_postmaster_start_time() AS started')).rows[0].started;
    await writeFile(path, JSON.stringify({ key: secret.toString('base64'), activeRoot, active, revoked, uncertain, fenced, ambiguous, before }), { mode: 0o600 });
    console.log('PASS database restart fixtures prepared (no identifiers or keys printed)');
  } else if (process.argv[2] === 'verify') {
    const saved = JSON.parse(await readFile(path, 'utf8'));
    const store = session(new CredentialVault('v1', { v1: Buffer.from(saved.key, 'base64') }));
    const after = (await db.query('SELECT pg_postmaster_start_time() AS started')).rows[0].started;
    assert.notEqual(after.toISOString(), saved.before);
    assert.ok(await store.lookup(saved.active));
    assert.equal(await store.withAccess(saved.active, async token => Boolean(token)), true);
    console.log('PASS database restart: committed active session and ciphertext survive');
    for (const [name, expected] of [['revoked', 'revoked'], ['uncertain', 'uncertain'], ['fenced', 'refreshing'], ['ambiguous', 'retired']]) {
      assert.equal(await store.lookup(saved[name]), null);
      await assert.rejects(store.refresh(saved[name], async () => assert.fail()), SessionError);
      const row = (await db.query('SELECT status FROM bff_sessions.sessions WHERE identifier_hash=$1', [hashIdentifier(saved[name])])).rows[0];
      assert.equal(row.status, expected);
      console.log(`PASS database restart: ${expected} remains blocked`);
    }
    await store.revoke(saved.activeRoot);
    assert.equal(await store.lookup(saved.active), null);
    console.log('PASS database restart: retired root logout revokes the surviving successor');
  } else { assert.fail('Explicit prepare/verify phase required'); }
} finally { resetFaults(); await Promise.all([...sessions.map(store => store.close()), db.end()]); }
