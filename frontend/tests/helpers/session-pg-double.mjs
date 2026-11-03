// Test-only pg boundary. No sockets. Production never imports this module.
const databases = [];
let nextPort = 40000;
export class DatabaseDouble {
  rows = []; calls = []; releases = []; locks = []; connects = 0;
  outage = false; loseClaim = false; loseFinish = false; failQuarantine = false;
  failInsert = false; failCommitBefore = false; afterCommit;
  constructor() {
    this.settings = { host: '127.0.0.1', port: nextPort++, database: 'scrapmart_bff_local_test',
      user: 'scrapmart_bff_runtime', password: 'synthetic-test-only' };
    databases.push(this);
  }
  get row() { return this.rows[0]; }
  async lock(hash, client) {
    let existing = this.locks.find(lock => lock.hash === hash);
    while (existing && existing.client !== client) {
      await new Promise(resolve => existing.waiters.push(resolve));
      existing = this.locks.find(lock => lock.hash === hash);
    }
    if (!existing) this.locks.push({ hash, client, waiters: [] });
  }
  unlock(client) {
    const released = this.locks.filter(lock => lock.client === client);
    this.locks = this.locks.filter(lock => lock.client !== client);
    for (const lock of released) for (const wake of lock.waiters) wake();
  }
}
class ClientDouble {
  writes = []; transaction = false;
  constructor(db) { this.db = db; }
  on() {}
  removeListener() {}
  read(hash) { return this.writes.findLast(row => row.hash === hash) ?? this.db.rows.find(row => row.hash === hash); }
  save(row) {
    if (this.transaction) this.writes.push(row);
    else this.apply(row);
  }
  apply(row) {
    const index = this.db.rows.findIndex(r => r.hash === row.hash);
    if (index < 0) this.db.rows.push(row); else this.db.rows[index] = row;
  }
  async query(sql, values = []) {
    const d = this.db; d.calls.push({ sql, values });
    if (d.outage) throw new Error('sensitive driver error');
    if (sql === 'BEGIN') { this.transaction = true; return { rows: [] }; }
    if (sql === 'ROLLBACK') { this.writes = []; this.transaction = false; d.unlock(this); return { rows: [] }; }
    if (sql === 'COMMIT') {
      if (d.failCommitBefore) throw new Error('synthetic commit failure');
      for (const row of this.writes) this.apply(row);
      this.writes = []; this.transaction = false; d.unlock(this);
      if (d.afterCommit) await d.afterCommit();
      if (d.loseFinish) throw new Error('synthetic lost commit acknowledgment');
      return { rows: [] };
    }
    const [hash, attempt] = values;
    if (sql.includes('INSERT INTO')) {
      const successor = values.length === 4;
      if (successor && d.failInsert) throw new Error('synthetic insert failure');
      const expires_at = successor ? values[3] : values[2];
      if (expires_at <= new Date()) return { rows: [] };
      this.save({ hash, identifier_hash: hash, root_hash: successor ? values[1] : hash,
        envelope: JSON.parse(successor ? values[2] : values[1]), status: 'active', expires_at, revoked_at: null });
      return { rows: [{ identifier_hash: hash }] };
    }
    let r = this.read(hash);
    if (!r) return { rows: [] };
    if (sql.includes("SET status='revoked'")) {
      await d.lock(r.root_hash, this); r = this.read(r.root_hash);
      this.save({ ...r, status: 'revoked', envelope: null, revoked_at: new Date() }); return { rows: [] };
    }
    if (sql.includes("SET status='uncertain'")) {
      if (d.failQuarantine) throw new Error('synthetic quarantine failure');
      if (r.status === 'refreshing' && r.attempt === attempt) this.save({ ...r, status: 'uncertain', envelope: null });
      return { rows: [] };
    }
    if (sql.includes("SET status='refreshing'")) {
      await d.lock(hash, this); r = this.read(hash);
      const root = this.read(r.root_hash);
      if (r.status !== 'active' || r.expires_at <= new Date() || root.revoked_at || root.expires_at <= new Date()) return { rows: [] };
      this.save({ ...r, status: 'refreshing', attempt });
      if (d.loseClaim) throw new Error('synthetic lost claim acknowledgment');
      return { rows: [{ envelope: r.envelope }] };
    }
    if (sql.includes('FOR UPDATE OF root')) {
      await d.lock(r.root_hash, this); const root = this.read(r.root_hash);
      return { rows: root.revoked_at || root.expires_at <= new Date() ? [] : [{ identifier_hash: root.hash }] };
    }
    if (sql.includes("SET status='retired'")) {
      if (r.status !== 'refreshing' || r.attempt !== attempt || r.expires_at <= new Date()) return { rows: [] };
      this.save({ ...r, status: 'retired', envelope: null });
      return { rows: [{ root_hash: r.root_hash, expires_at: r.expires_at }] };
    }
    const root = this.read(r.root_hash);
    return { rows: r.status === 'active' && r.expires_at > new Date() && !root.revoked_at && root.expires_at > new Date() ? [{ ...r }] : [] };
  }
  release(destroy) { this.db.unlock(this); this.db.releases.push(Boolean(destroy)); }
}
export class Pool {
  #db; #closed = false;
  constructor(settings) {
    this.#db = databases.find(db => db.settings.port === settings.port);
    if (!this.#db) throw new Error('Unexpected offline pool configuration; no connection attempted');
  }
  on() {}
  async connect() {
    if (this.#closed || this.#db.outage) throw new Error('synthetic unavailable database');
    this.#db.connects++; return new ClientDouble(this.#db);
  }
  async end() { this.#closed = true; }
}
