import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { networkInterfaces } from 'node:os';
import { randomBytes, randomUUID } from 'node:crypto';
import { Pool } from 'pg';
import { CredentialVault, newIdentifier, hashIdentifier, SessionError } from '../../src/lib/server/sessions/crypto.ts';
import { SessionStore } from '../../src/lib/server/sessions/store.ts';

export { CredentialVault, newIdentifier, hashIdentifier, SessionError, SessionStore };
export const sessions = [];
export function connection(extra = {}) {
  return { host: '127.0.0.1', port: 5432, database: 'scrapmart_bff_local_test',
    user: 'scrapmart_bff_runtime', password: 'synthetic-trust-only', ...extra };
}
export function session(vault, extra = {}) {
  const store = new SessionStore(connection(extra), vault); sessions.push(store); return store;
}
export async function guard() {
  assert.equal(process.env.SCRAPMART_BFF_ISOLATED_TEST, '1');
  const marker = JSON.parse(await readFile(new URL('../../ISOLATED.json', import.meta.url), 'utf8'));
  assert.equal(marker.batch, '3b3'); assert.equal(marker.database, 'scrapmart_bff_local_test');
  for (const [name, addresses] of Object.entries(networkInterfaces())) {
    assert.equal(name, 'lo', 'Only loopback is allowed');
    assert.ok(addresses.every(address => address.internal));
  }
  assert.ok(Object.keys(networkInterfaces()).includes('lo'));
}
export function pool(user = 'scrapmart_bff_runtime', extra = {}) {
  assert.ok(['postgres', 'scrapmart_bff_runtime'].includes(user));
  return new Pool({ host: '127.0.0.1', port: 5432, database: 'scrapmart_bff_local_test',
    user, password: 'synthetic-trust-only', ssl: false, max: 6,
    connectionTimeoutMillis: 500, statement_timeout: 2500, query_timeout: 3000,
    application_name: `bff-3b3-${randomUUID()}`, ...extra });
}
export async function identity(db, user) {
  const { rows: [row] } = await db.query(`SELECT current_database() AS db, current_user AS role,
    current_setting('server_version_num')::int AS version, host(inet_server_addr()) AS address`);
  assert.equal(row.db, 'scrapmart_bff_local_test'); assert.equal(row.role, user);
  assert.ok(row.version >= 160000 && row.version < 170000); assert.equal(row.address, '127.0.0.1');
}
export function key() { return randomBytes(32); }
export function credentials() {
  return { accessToken: `synthetic-${randomUUID()}`, refreshCookie: newIdentifier(),
    accessExpiresAt: new Date(Date.now() + 60000).toISOString() };
}
export const expiry = () => new Date(Date.now() + 300000);
export function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}
export async function until(check) {
  const deadline = Date.now() + 3000;
  do {
    if (await check()) return;
    await new Promise(resolve => setTimeout(resolve, 20));
  } while (Date.now() < deadline);
  assert.fail('Timed out waiting for verified PostgreSQL lock/state');
}
