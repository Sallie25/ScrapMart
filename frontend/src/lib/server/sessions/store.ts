import 'server-only';
import { randomUUID } from 'node:crypto';
import { CredentialVault, SessionError, hashIdentifier, newIdentifier } from './crypto';
import type { Credentials, Envelope } from './crypto';
import { OwnedSessionDatabase } from './database';
import type { SessionConnectionSettings } from './database';

// No timers, process-local locks, automatic retries or recoverable refresh leases.
// A private pool commits the claim before upstream dispatch. Completion rotates
// browser identifiers atomically; an ambiguous commit cannot reactivate the old ID.
export class SessionStore {
  #db: OwnedSessionDatabase;
  #vault: CredentialVault;
  constructor(settings: SessionConnectionSettings, vault: CredentialVault) {
    this.#db = new OwnedSessionDatabase(settings); this.#vault = vault;
  }
  async #query(sql: string, values: unknown[] = []) {
    try { return await this.#db.query(sql, values); }
    catch { throw new SessionError(); }
  }
  async create(credentials: Credentials, expiresAt: Date): Promise<string> {
    if (!Number.isFinite(expiresAt.getTime())) throw new SessionError();
    const identifier = newIdentifier();
    const hash = hashIdentifier(identifier);
    const sealed = this.#vault.seal(hash, credentials);
    const rows = await this.#query(`INSERT INTO bff_sessions.sessions
      (identifier_hash, root_hash, envelope, expires_at) SELECT $1, $1, $2::jsonb, $3::timestamptz
      WHERE $3::timestamptz > clock_timestamp() RETURNING identifier_hash`, [hash, JSON.stringify(sealed), expiresAt]);
    if (rows.length !== 1) throw new SessionError();
    return identifier;
  }
  async lookup(identifier: string): Promise<{ expiresAt: Date } | null> {
    const rows = await this.#query(`SELECT s.expires_at FROM bff_sessions.sessions s
      JOIN bff_sessions.sessions root ON root.identifier_hash=s.root_hash
      WHERE s.identifier_hash=$1 AND s.status='active' AND s.expires_at > clock_timestamp()
      AND root.revoked_at IS NULL AND root.expires_at > clock_timestamp()`, [hashIdentifier(identifier)]);
    if (!rows.length) return null;
    const expiresAt = new Date(rows[0].expires_at as string | Date);
    if (!Number.isFinite(expiresAt.getTime())) throw new SessionError();
    return { expiresAt };
  }
  // Internal server-side callback boundary. Never return credentials from a route/action.
  async withAccess<T>(identifier: string, consume: (accessToken: string) => Promise<T>): Promise<T> {
    const hash = hashIdentifier(identifier);
    const rows = await this.#query(`SELECT s.envelope FROM bff_sessions.sessions s
      JOIN bff_sessions.sessions root ON root.identifier_hash=s.root_hash
      WHERE s.identifier_hash=$1 AND s.status='active' AND s.expires_at > clock_timestamp()
      AND root.revoked_at IS NULL AND root.expires_at > clock_timestamp()`, [hash]);
    if (rows.length !== 1) throw new SessionError();
    const credentials = this.#vault.open(hash, rows[0].envelope as Envelope);
    if (Date.parse(credentials.accessExpiresAt) <= Date.now()) throw new SessionError();
    return consume(credentials.accessToken);
  }
  async revoke(identifier: string): Promise<void> {
    await this.#query(`UPDATE bff_sessions.sessions SET status='revoked', envelope=NULL,
      revoked_at=clock_timestamp() WHERE identifier_hash=(
        SELECT root_hash FROM bff_sessions.sessions WHERE identifier_hash=$1)
      AND status <> 'revoked'`, [hashIdentifier(identifier)]);
  }
  async close(): Promise<void> { await this.#db.close(); }
  // The caller must replace the browser cookie with the returned ID. Never
  // resend the old identifier on success, and never recover undisclosed successors.
  async refresh(identifier: string, upstream: (refreshCookie: string) => Promise<Credentials>): Promise<string> {
    const hash = hashIdentifier(identifier);
    const attempt = randomUUID();
    // Durable single-use claim. A lost claim acknowledgment never triggers upstream.
    const rows = await this.#query(`UPDATE bff_sessions.sessions AS s SET status='refreshing',
      refresh_attempt=$2, refresh_started_at=clock_timestamp()
      WHERE identifier_hash=$1 AND status='active' AND expires_at > clock_timestamp()
      AND EXISTS (SELECT 1 FROM bff_sessions.sessions root WHERE root.identifier_hash=s.root_hash
        AND root.revoked_at IS NULL AND root.expires_at > clock_timestamp())
      RETURNING envelope`, [hash, attempt]);
    if (rows.length !== 1) throw new SessionError();
    try {
      const current = this.#vault.open(hash, rows[0].envelope as Envelope);
      // Exactly one invocation, including on transport/timeout errors.
      const replacement = await upstream(current.refreshCookie);
      if (replacement.refreshCookie === current.refreshCookie) throw new SessionError();
      const successor = newIdentifier();
      const successorHash = hashIdentifier(successor);
      const sealed = this.#vault.seal(successorHash, replacement);
      await this.#db.transaction(async query => {
        // Serialize completion with family-wide logout using the stable root.
        const roots = await query(`SELECT root.identifier_hash FROM bff_sessions.sessions s
          JOIN bff_sessions.sessions root ON root.identifier_hash=s.root_hash
          WHERE s.identifier_hash=$1 AND root.revoked_at IS NULL
          AND root.expires_at > clock_timestamp() FOR UPDATE OF root`, [hash]);
        if (roots.length !== 1) throw new SessionError();
        const retired = await query(`UPDATE bff_sessions.sessions SET status='retired', envelope=NULL
          WHERE identifier_hash=$1 AND status='refreshing' AND refresh_attempt=$2
          AND expires_at > clock_timestamp() RETURNING root_hash, expires_at`, [hash, attempt]);
        if (retired.length !== 1) throw new SessionError();
        await query(`INSERT INTO bff_sessions.sessions
          (identifier_hash,root_hash,envelope,expires_at) VALUES($1,$2,$3::jsonb,$4)`,
        [successorHash, retired[0].root_hash, JSON.stringify(sealed), retired[0].expires_at]);
      });
      return successor;
    } catch {
      // Cleanup is best-effort, not the security boundary. Before completion the
      // old ID is refreshing; after completion it is retired. Both deny use even
      // when this write fails. An orphan successor is never disclosed or recovered.
      try {
        await this.#query(`UPDATE bff_sessions.sessions SET status='uncertain', envelope=NULL
          WHERE identifier_hash=$1 AND status='refreshing' AND refresh_attempt=$2`, [hash, attempt]);
      } catch { /* No credential is returned, even if the quarantine cannot persist. */ }
      throw new SessionError();
    }
  }
}
