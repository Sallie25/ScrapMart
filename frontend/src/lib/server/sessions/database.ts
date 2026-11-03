import 'server-only';
import { Pool } from 'pg';
import type { PoolClient } from 'pg';
import { SessionError } from './crypto';

export type SessionConnectionSettings = Readonly<{
  host: '127.0.0.1'; port: number; database: 'scrapmart_bff_local_test';
  user: 'scrapmart_bff_runtime'; password: string;
}>;
type Rows = Record<string, unknown>[];
const ignoreClientError = () => {}; // Query failures are returned as generic SessionError.

// The pool and its clients never escape this module. Callers cannot BEGIN on
// these connections or supply their own transaction-bound query implementation.
export class OwnedSessionDatabase {
  #pool: Pool;
  constructor(settings: SessionConnectionSettings) {
    try {
      if (!settings || ![Object.prototype, null].includes(Object.getPrototypeOf(settings))) throw new SessionError();
      const descriptors = Object.getOwnPropertyDescriptors(settings);
      const names = ['host', 'port', 'database', 'user', 'password'];
      if (Object.keys(descriptors).length !== names.length ||
          names.some(name => !descriptors[name] || !('value' in descriptors[name]))) throw new SessionError();
      if (settings.host !== '127.0.0.1' || settings.database !== 'scrapmart_bff_local_test' ||
          settings.user !== 'scrapmart_bff_runtime' || !Number.isInteger(settings.port) ||
          settings.port < 1024 || settings.port > 65535 || typeof settings.password !== 'string' ||
          !settings.password) throw new SessionError();
      this.#pool = new Pool({ host: settings.host, port: settings.port, database: settings.database,
        user: settings.user, password: settings.password, ssl: false, max: 4,
        options: '-c synchronous_commit=on',
        connectionTimeoutMillis: 2000, idleTimeoutMillis: 10000,
        statement_timeout: 5000, query_timeout: 6000, application_name: 'scrapmart-bff-local' });
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
