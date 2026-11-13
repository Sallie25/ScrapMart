// Test-loader-only driver instrumentation around REAL pg clients. Never used
// by Next/application imports. No connection is opened by importing this file.
import { Pool as RealPool } from 'pg';
export const ownedPools = [];
export const faults = {};
export function resetFaults() { for (const name of Object.keys(faults)) delete faults[name]; }
export class Pool extends RealPool {
  constructor(settings) { super(settings); ownedPools.push(this); }
  async connect() {
    const client = await super.connect();
    const query = client.query.bind(client);
    if (faults.statementTimeout) await query('SET statement_timeout=' + Number(faults.statementTimeout));
    return {
      on: (event, listener) => client.on(event, listener),
      removeListener: (event, listener) => client.removeListener(event, listener),
      query: async (sql, values) => {
        if (faults.terminateNext) {
          delete faults.terminateNext;
          try { await query('SELECT pg_terminate_backend(pg_backend_pid())'); } catch { /* Real disconnect. */ }
        }
        if (sql.includes("SET status='uncertain'") && faults.failQuarantine) throw new Error('synthetic quarantine outage');
        if (sql.includes('VALUES($1,$2,$3::jsonb,$4)') && faults.failCompletion) throw new Error('synthetic completion outage');
        const result = await query(sql, values);
        if (sql.includes("SET status='refreshing'") && faults.loseClaim) {
          delete faults.loseClaim; throw new Error('synthetic lost claim acknowledgment');
        }
        if (sql === 'COMMIT') {
          if (faults.afterCommit) await faults.afterCommit();
          if (faults.loseCommit) { delete faults.loseCommit; throw new Error('synthetic lost completion acknowledgment'); }
        }
        return result;
      },
      release: destroy => client.release(destroy),
    };
  }
}
