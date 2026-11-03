import 'server-only';
import { Pool } from 'pg';
import type { PoolClient } from 'pg';
import { SessionError } from './crypto';

import { validateSessionSettings } from './connection-settings';
import type { SessionConnectionSettings } from './connection-settings';
export type { SessionConnectionSettings } from './connection-settings';

type Rows = Record<string, unknown>[];
const ignoreClientError = () => {}; // Query failures are returned as generic SessionError.

// The pool and its clients never escape this module. Callers cannot BEGIN on
// these connections or supply their own transaction-bound query implementation.
export class OwnedSessionDatabase {
  #pool: Pool;
  constructor(settings: SessionConnectionSettings) {
    try {
      validateSessionSettings(settings);
      const remote = 'mode' in settings;
      if (remote && process.env.NODE_TLS_REJECT_UNAUTHORIZED === '0') throw new SessionError();
      this.#pool = new Pool({ host: settings.host, port: settings.port, database: settings.database,
        user: settings.user, password: settings.password, ssl: remote ? {
          rejectUnauthorized: true, minVersion: 'TLSv1.2', servername: settings.host,
          ...('ca' in settings && settings.ca ? { ca: settings.ca } : {}),
        } : false, max: 4,
        options: remote ? '-c synchronous_commit=on -c search_path=pg_catalog,bff_sessions,pg_temp' : '-c synchronous_commit=on',
        connectionTimeoutMillis: 2000, idleTimeoutMillis: 10000,
        statement_timeout: 5000, query_timeout: 6000, application_name: remote ? 'scrapmart-bff-runtime' : 'scrapmart-bff-local' });
      this.#pool.on('error', () => {});
    } catch { throw new SessionError(); }
  }
  async #client(): Promise<PoolClient> {
    try {
      const client = await this.#pool.connect();
      client.on('error', ignoreClientError);
      return client;
    } catch { throw new SessionError(); }
  }
  #release(client: PoolClient, destroy: boolean): void {
    client.removeListener('error', ignoreClientError);
    client.release(destroy);
  }
  async query(sql: string, values: unknown[] = []): Promise<Rows> {
    const client = await this.#client();
    let destroy = false;
    try { return (await client.query(sql, values)).rows; }
    catch { destroy = true; throw new SessionError(); }
    finally { this.#release(client, destroy); }
  }
  async transaction<T>(operation: (query: (sql: string, values?: unknown[]) => Promise<Rows>) => Promise<T>): Promise<T> {
    const client = await this.#client();
    let destroy = false;
    try {
      await client.query('BEGIN');
      const result = await operation(async (sql, values = []) => (await client.query(sql, values)).rows);
      await client.query('COMMIT');
      return result; // Only an acknowledged COMMIT releases a successor identifier.
    } catch {
      destroy = true;
      try { await client.query('ROLLBACK'); } catch { /* Never reuse an uncertain connection. */ }
      throw new SessionError();
    } finally { this.#release(client, destroy); }
  }
  async close(): Promise<void> {
    try { await this.#pool.end(); } catch { throw new SessionError(); }
  }
}
