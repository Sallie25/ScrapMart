import test from 'node:test';
import assert from 'node:assert/strict';
import { fork } from 'node:child_process';

if (process.env.SCRAPMART_BFF_ISOLATED_TEST !== '1') {
  test('PostgreSQL integration requires the verified isolated runner', { skip: true }, () => {});
} else {
  test('isolated PostgreSQL session store', { timeout: 60000 }, async t => {
  const h = await import('./helpers/postgres-fixture.mjs');
  await h.guard();
  const { faults, resetFaults, ownedPools } = await import('./helpers/postgres-pg-faults.mjs');
  t.beforeEach(resetFaults);
  const admin = h.pool('postgres'), db = h.pool(), other = h.pool();
  t.after(async () => { resetFaults(); await Promise.all([...h.sessions.map(store => store.close()), admin.end(), db.end(), other.end()]); });
  await h.identity(admin, 'postgres'); await h.identity(db, 'scrapmart_bff_runtime'); await h.identity(other, 'scrapmart_bff_runtime');
  const secret = h.key(), vault = new h.CredentialVault('v1', { v1: secret });
  const store = h.session(vault);
  const second = h.session(vault);
  async function fixture(expiry = h.expiry(), credentials = h.credentials()) {
    const id = await store.create(credentials, expiry);
    return { id, hash: h.hashIdentifier(id), credentials };
  }
  async function row(hash) {
    return (await admin.query('SELECT * FROM bff_sessions.sessions WHERE identifier_hash=$1', [hash])).rows[0];
  }

  async function scenario(name, run) {
    let failed = false;
    await t.test(name, async () => {
      try { await run(); } catch (error) { failed = true; throw error; }
    });
    if (failed) throw new Error('Stopped after failing PostgreSQL security scenario: ' + name);
  }

  await scenario('schema ownership, role attributes, grants and PUBLIC restrictions', async () => {
    const { rows: [role] } = await admin.query(`SELECT rolsuper,rolcreatedb,rolcreaterole,rolinherit,
      rolreplication,rolbypassrls FROM pg_roles WHERE rolname='scrapmart_bff_runtime'`);
    assert.ok(Object.values(role).every(value => value === false));
    const { rows: [owners] } = await admin.query(`SELECT pg_get_userbyid(c.relowner) AS table_owner,
      pg_get_userbyid(n.nspowner) AS schema_owner FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='bff_sessions' AND c.relname='sessions'`);
    assert.equal(owners.table_owner, 'postgres'); assert.equal(owners.schema_owner, 'postgres');
    const { rows: [acl] } = await db.query(`SELECT
      has_database_privilege(current_user,current_database(),'CREATE') AS db_create,
      has_database_privilege(current_user,current_database(),'TEMP') AS temp,
      has_schema_privilege(current_user,'bff_sessions','CREATE') AS schema_create`);
    assert.ok(Object.values(acl).every(value => value === false));
    const memberships = await admin.query(`SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member
      WHERE r.rolname='scrapmart_bff_runtime'`);
    assert.equal(memberships.rowCount, 0);
  });

  await scenario('restricted role can create, lookup and use encrypted sessions', async () => {
    const f = await fixture(); const r = await row(f.hash);
    assert.equal(r.identifier_hash, h.hashIdentifier(f.id)); assert.notEqual(r.identifier_hash, f.id);
    assert.ok(!JSON.stringify(r).includes(f.credentials.accessToken));
    assert.ok(!JSON.stringify(r).includes(f.credentials.refreshCookie));
    assert.ok(await store.lookup(f.id));
    assert.equal(await store.withAccess(f.id, async token => token === f.credentials.accessToken), true);
  });

  await scenario('runtime denies DDL, DELETE, TRUNCATE, protected columns and privilege escalation', async () => {
    const f = await fixture();
    for (const sql of [
      'CREATE TABLE bff_sessions.forbidden(id int)', 'CREATE SCHEMA forbidden',
      'CREATE TEMP TABLE forbidden(id int)', 'DROP TABLE bff_sessions.sessions',
      'DELETE FROM bff_sessions.sessions', 'TRUNCATE bff_sessions.sessions',
      "UPDATE bff_sessions.sessions SET identifier_hash=identifier_hash WHERE identifier_hash=$1",
      "UPDATE bff_sessions.sessions SET expires_at=expires_at WHERE identifier_hash=$1",
      "UPDATE bff_sessions.sessions SET created_at=created_at WHERE identifier_hash=$1",
      "UPDATE bff_sessions.sessions SET root_hash=root_hash WHERE identifier_hash=$1",
      'SET ROLE postgres', 'ALTER ROLE scrapmart_bff_runtime CREATEDB',
    ]) {
      await assert.rejects(db.query(sql, sql.includes('$1') ? [f.hash] : []), error => error.code === '42501', sql);
    }
    // PostgreSQL may report an unauthorized GRANT as a warning/no-op. Assert
    // the security outcome in the catalogs rather than requiring an exception.
    await db.query('GRANT ALL ON bff_sessions.sessions TO PUBLIC');
    const publicGrants = await admin.query(`SELECT count(*)::int AS count FROM pg_class c
      JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN LATERAL aclexplode(c.relacl) a
      WHERE n.nspname='bff_sessions' AND c.relname='sessions' AND a.grantee=0`);
    assert.equal(publicGrants.rows[0].count, 0);
    const grantOption = await db.query(`SELECT has_table_privilege(current_user,
      'bff_sessions.sessions','SELECT WITH GRANT OPTION') AS permitted`);
    assert.equal(grantOption.rows[0].permitted, false);
  });

  await scenario('SQL rejects inconsistent lifecycle states, invalid hashes and invalid expiry', async () => {
    const f = await fixture();
    for (const sql of [
      "UPDATE bff_sessions.sessions SET status='other' WHERE identifier_hash=$1",
      "UPDATE bff_sessions.sessions SET status='refreshing' WHERE identifier_hash=$1",
      "UPDATE bff_sessions.sessions SET status='revoked' WHERE identifier_hash=$1",
      "UPDATE bff_sessions.sessions SET envelope=NULL WHERE identifier_hash=$1",
    ]) await assert.rejects(db.query(sql, [f.hash]), error => error.code === '23514');
    await assert.rejects(db.query(`INSERT INTO bff_sessions.sessions(identifier_hash,root_hash,envelope,expires_at)
      VALUES('bad',$1,'{}',clock_timestamp()+interval '1 minute')`, [f.hash]), error => error.code === '23514');
    await assert.rejects(admin.query('UPDATE bff_sessions.sessions SET expires_at=created_at WHERE identifier_hash=$1', [f.hash]), error => error.code === '23514');
  });

  await scenario('independent connections admit exactly one concurrent refresh owner', async () => {
    const f = await fixture(); const entered = h.deferred(), release = h.deferred(); let calls = 0;
    const replacement = h.credentials();
    const first = store.refresh(f.id, async cookie => {
      assert.ok(cookie === f.credentials.refreshCookie); calls++; entered.resolve(); await release.promise; return replacement;
    });
    try {
      await entered.promise;
      assert.equal((await row(f.hash)).status, 'refreshing');
      assert.equal(await second.lookup(f.id), null);
      await assert.rejects(second.refresh(f.id, async () => { calls++; return h.credentials(); }), h.SessionError);
    } finally { release.resolve(); }
    const successor = await first; assert.equal(calls, 1);
    assert.equal((await row(f.hash)).status, 'retired');
    assert.equal(await store.lookup(f.id), null); assert.ok(await second.lookup(successor));
    const hash = h.hashIdentifier(successor);
    assert.ok(vault.open(hash, (await row(hash)).envelope).refreshCookie === replacement.refreshCookie);
  });

  await scenario('actual row locking blocks refresh and rechecks predicate after competing revocation commits', async () => {
    const f = await fixture(), locker = await admin.connect();
    let pending, dispatched = false;
    try {
      await locker.query('BEGIN');
      const pid = (await locker.query('SELECT pg_backend_pid() AS pid')).rows[0].pid;
      await locker.query('SELECT identifier_hash FROM bff_sessions.sessions WHERE identifier_hash=$1 FOR UPDATE', [f.hash]);
      pending = second.refresh(f.id, async () => { dispatched = true; return h.credentials(); });
      const rejected = assert.rejects(pending, h.SessionError);
      await h.until(async () => (await admin.query(`SELECT EXISTS(SELECT 1 FROM pg_stat_activity
        WHERE $1::int=ANY(pg_blocking_pids(pid)) AND wait_event_type='Lock') AS waiting`, [pid])).rows[0].waiting);
      assert.equal(dispatched, false);
      await locker.query(`UPDATE bff_sessions.sessions SET status='revoked',envelope=NULL,
        revoked_at=clock_timestamp() WHERE identifier_hash=$1`, [f.hash]);
      await locker.query('COMMIT'); await rejected;
      assert.equal(dispatched, false); assert.equal((await row(f.hash)).status, 'revoked');
    } finally { await locker.query('ROLLBACK'); locker.release(); }
  });

  await scenario('real statement timeout while claiming refresh never dispatches upstream', async () => {
    const f = await fixture(), locker = await admin.connect();
    faults.statementTimeout = 80;
    const limited = h.session(vault);
    try {
      await locker.query('BEGIN');
      await locker.query('SELECT identifier_hash FROM bff_sessions.sessions WHERE identifier_hash=$1 FOR UPDATE', [f.hash]);
      await assert.rejects(limited.refresh(f.id, async () => assert.fail()), h.SessionError);
    } finally { await locker.query('ROLLBACK'); locker.release(); }
    assert.equal((await row(f.hash)).status, 'active');
  });

  await scenario('transaction-bound clients and shared pools are rejected before dispatch', async () => {
    const client = await db.connect();
    try {
      await client.query('BEGIN');
      assert.throws(() => new h.SessionStore(client, vault), h.SessionError);
      assert.throws(() => new h.SessionStore(db, vault), h.SessionError);
      assert.throws(() => new h.SessionStore({ query: () => assert.fail() }, vault), h.SessionError);
    } finally { await client.query('ROLLBACK'); client.release(); }
  });

  await scenario('database-clock expiration denies lookup/access/refresh and rejects expired creation', async () => {
    const f = await fixture(new Date(Date.now() + 400));
    await h.until(async () => (await admin.query('SELECT expires_at<=clock_timestamp() AS expired FROM bff_sessions.sessions WHERE identifier_hash=$1', [f.hash])).rows[0].expired);
    assert.equal(await store.lookup(f.id), null);
    await assert.rejects(store.withAccess(f.id, async () => assert.fail()), h.SessionError);
    await assert.rejects(store.refresh(f.id, async () => assert.fail()), h.SessionError);
    await assert.rejects(store.create(h.credentials(), new Date(0)), h.SessionError);
  });

  await scenario('expiry during upstream refresh cannot extend or reactivate the session', async () => {
    const f = await fixture(new Date(Date.now() + 400));
    await assert.rejects(store.refresh(f.id, async () => {
      await h.until(async () => (await admin.query('SELECT expires_at<=clock_timestamp() AS expired FROM bff_sessions.sessions WHERE identifier_hash=$1', [f.hash])).rows[0].expired);
      return h.credentials();
    }), h.SessionError);
    assert.equal(await store.lookup(f.id), null); assert.equal((await row(f.hash)).status, 'uncertain');
  });

  await scenario('logout before refresh prevents any upstream dispatch', async () => {
    const f = await fixture(); await store.revoke(f.id); await store.revoke(f.id);
    await assert.rejects(second.refresh(f.id, async () => assert.fail()), h.SessionError);
    assert.equal(await store.lookup(f.id), null); assert.equal((await row(f.hash)).envelope, null);
  });

  await scenario('logout during refresh fences late completion across independent pools', async () => {
    const f = await fixture(); const entered = h.deferred(), release = h.deferred();
    const pending = store.refresh(f.id, async () => { entered.resolve(); await release.promise; return h.credentials(); });
    const rejected = assert.rejects(pending, h.SessionError);
    try { await entered.promise; await second.revoke(f.id); } finally { release.resolve(); }
    await rejected;
    assert.equal((await row(f.hash)).status, 'revoked'); assert.equal((await row(f.hash)).envelope, null);
  });

  await scenario('lost upstream response quarantines permanently without replay', async () => {
    const f = await fixture(); let calls = 0;
    await assert.rejects(store.refresh(f.id, async () => { calls++; throw new Error('synthetic transport loss'); }), h.SessionError);
    await assert.rejects(second.refresh(f.id, async () => { calls++; return h.credentials(); }), h.SessionError);
    assert.equal(calls, 1); assert.equal((await row(f.hash)).status, 'uncertain');
    assert.equal((await row(f.hash)).envelope, null);
  });

  await scenario('sequential rotation sends only replacement and rejects an unchanged cookie', async () => {
    const f = await fixture(); const replacement = h.credentials();
    const successor = await store.refresh(f.id, async () => replacement);
    await assert.rejects(store.refresh(successor, async cookie => {
      assert.ok(cookie === replacement.refreshCookie && cookie !== f.credentials.refreshCookie); return replacement;
    }), h.SessionError);
    assert.equal((await row(h.hashIdentifier(successor))).status, 'uncertain');
  });

  await scenario('lost acknowledgment of a real committed claim never dispatches upstream', async () => {
    const f = await fixture(); faults.loseClaim = true;
    await assert.rejects(store.refresh(f.id, async () => assert.fail()), h.SessionError);
    assert.equal((await row(f.hash)).status, 'refreshing'); assert.equal(await second.lookup(f.id), null);
  });

  await scenario('lost completion acknowledgment permanently retires the browser identifier', async () => {
    const f = await fixture(); faults.loseCommit = true;
    await assert.rejects(store.refresh(f.id, async () => h.credentials()), h.SessionError);
    assert.equal((await row(f.hash)).status, 'retired'); assert.equal(await second.lookup(f.id), null);
    await assert.rejects(second.refresh(f.id, async () => assert.fail()), h.SessionError);
  });

  await scenario('failed completion and quarantine writes preserve the durable refresh fence', async () => {
    const f = await fixture(); faults.failCompletion = true; faults.failQuarantine = true;
    await assert.rejects(store.refresh(f.id, async () => h.credentials()), h.SessionError);
    assert.equal((await row(f.hash)).status, 'refreshing'); assert.equal(await second.lookup(f.id), null);
  });

  await scenario('committed completion plus lost acknowledgment and failed quarantine cannot revive the browser identifier', async () => {
    const f = await fixture(); faults.loseCommit = true; faults.failQuarantine = true;
    await assert.rejects(store.refresh(f.id, async () => h.credentials()), h.SessionError);
    assert.equal((await row(f.hash)).status, 'retired');
    const successors = await admin.query("SELECT identifier_hash FROM bff_sessions.sessions WHERE root_hash=$1 AND status='active'", [f.hash]);
    assert.equal(successors.rowCount, 1); // Hashed orphan only; its browser ID was never returned.
    assert.equal(await second.lookup(f.id), null);
    await assert.rejects(second.withAccess(f.id, async () => assert.fail()), h.SessionError);
    await assert.rejects(second.refresh(f.id, async () => assert.fail()), h.SessionError);
  });

  await scenario('malformed ciphertext, swapped row binding and unknown versions deny credential use', async () => {
    for (const mutation of ['tag', 'binding', 'version']) {
      const f = await fixture(); const envelope = (await row(f.hash)).envelope;
      if (mutation === 'tag') envelope.tag = Buffer.alloc(16).toString('base64');
      if (mutation === 'version') envelope.version = 'unknown';
      if (mutation === 'binding') {
        const another = await fixture(); Object.assign(envelope, (await row(another.hash)).envelope);
      }
      await db.query('UPDATE bff_sessions.sessions SET envelope=$2::jsonb WHERE identifier_hash=$1', [f.hash, JSON.stringify(envelope)]);
      await assert.rejects(store.withAccess(f.id, async () => assert.fail()), h.SessionError);
      await assert.rejects(store.refresh(f.id, async () => assert.fail()), h.SessionError);
      assert.equal((await row(f.hash)).status, 'uncertain');
    }
  });

  await scenario('retained old keys decrypt and rotation reencrypts with the current version', async () => {
    const f = await fixture(); const nextKey = h.key();
    const rotated = h.session(new h.CredentialVault('v2', { v1: secret, v2: nextKey }));
    assert.equal(await rotated.withAccess(f.id, async token => token === f.credentials.accessToken), true);
    const successor = await rotated.refresh(f.id, async () => h.credentials());
    assert.equal((await row(h.hashIdentifier(successor))).envelope.version, 'v2');
    await assert.rejects(store.withAccess(successor, async () => assert.fail()), h.SessionError);
    assert.equal(await rotated.withAccess(successor, async token => Boolean(token)), true);
  });

  await scenario('real owned-pool exhaustion fails closed and recovers after release', async () => {
    const f = await fixture(), exhausted = h.session(vault), owned = ownedPools.at(-1), held = [];
    try {
      for (let i = 0; i < 4; i++) held.push(await owned.connect());
      await assert.rejects(exhausted.lookup(f.id), h.SessionError);
      await assert.rejects(exhausted.refresh(f.id, async () => assert.fail()), h.SessionError);
    } finally { for (const client of held) client.release(false); }
    assert.ok(await exhausted.lookup(f.id));
  });


  await scenario('real connection refusal and terminated owned connection fail closed', async () => {
    const f = await fixture(), failed = h.session(vault, { port: 65432 });
    await assert.rejects(failed.lookup(f.id), h.SessionError);
    await assert.rejects(failed.refresh(f.id, async () => assert.fail()), h.SessionError);
    faults.terminateNext = true;
    await assert.rejects(store.lookup(f.id), h.SessionError);
    assert.ok(await second.lookup(f.id));
  });

  await scenario('logout through a retired ancestor blocks the latest generation', async () => {
    const f = await fixture();
    const first = await store.refresh(f.id, async () => h.credentials());
    const latest = await second.refresh(first, async () => h.credentials());
    await store.revoke(first);
    for (const id of [f.id, first, latest]) {
      assert.equal(await second.lookup(id), null);
      await assert.rejects(second.refresh(id, async () => assert.fail()), h.SessionError);
    }
  });

  await scenario('logout after committed completion and before handoff blocks the late successor', async () => {
    const f = await fixture(), entered = h.deferred(), release = h.deferred();
    faults.afterCommit = async () => { entered.resolve(); await release.promise; };
    const pending = store.refresh(f.id, async () => h.credentials());
    try { await entered.promise; await second.revoke(f.id); } finally { release.resolve(); }
    const successor = await pending;
    assert.equal(await second.lookup(successor), null); assert.equal((await row(f.hash)).status, 'revoked');
  });

  async function worker(message, crash = false) {
    const child = fork(new URL('./helpers/postgres-process-worker.mjs', import.meta.url), [], {
      execArgv: ['--import', './tests/helpers/session-loader.mjs'],
      env: { SCRAPMART_BFF_ISOLATED_TEST: '1' }, silent: true,
    });
    const exit = new Promise(resolve => child.once('exit', resolve));
    const result = new Promise((resolve, reject) => {
      const timeout = setTimeout(() => { child.kill('SIGKILL'); reject(new Error('Worker timeout')); }, 5000);
      child.once('message', value => { clearTimeout(timeout); resolve(value); });
      child.once('error', error => { clearTimeout(timeout); reject(error); });
    });
    child.send({ ...message, key: secret.toString('base64') });
    try { const value = await result; if (crash) child.kill('SIGKILL'); await exit; return value; }
    finally { if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL'); }
  }

  await scenario('fresh Node processes recover committed sessions with the retained key', async () => {
    const f = await fixture();
    for (let i = 0; i < 2; i++) {
      const result = await worker({ id: f.id, access: f.credentials.accessToken });
      assert.equal(result.available, true); assert.equal(result.usable, true);
    }
  });

  await scenario('SIGKILL after committed claim leaves a permanent fence across process restart', async () => {
    const f = await fixture(); const result = await worker({ mode: 'claim-and-crash', id: f.id }, true);
    assert.equal(result.claimed, true); assert.equal((await row(f.hash)).status, 'refreshing');
    await assert.rejects(second.refresh(f.id, async () => assert.fail()), h.SessionError);
    assert.equal(await store.lookup(f.id), null);
  });
  });
}
