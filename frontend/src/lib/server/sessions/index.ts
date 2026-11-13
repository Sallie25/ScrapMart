import 'server-only';
import { CredentialVault, SessionError } from './crypto';
import { SessionStore } from './store';

// Explicit construction only; importing this module does not connect or read secrets.
export function createLocalSessionStore(env: NodeJS.ProcessEnv = process.env) {
  try {
    const version = env.BFF_SESSION_KEY_VERSION;
    const encoded = JSON.parse(env.BFF_SESSION_KEYS_JSON ?? '') as Record<string, string>;
    if (!version || !encoded || Array.isArray(encoded) || typeof encoded !== 'object') throw new SessionError();
    const keys = Object.fromEntries(Object.entries(encoded).map(([v, value]) => {
      if (typeof value !== 'string') throw new SessionError();
      const key = Buffer.from(value, 'base64');
      if (key.length !== 32 || key.toString('base64') !== value) throw new SessionError();
      return [v, key];
    }));
    const vault = new CredentialVault(version, keys);
    // Local-only guard for this batch. No arbitrary connection string or PG* fallback.
    const port = Number(env.BFF_SESSION_DB_PORT);
    if (env.BFF_SESSION_DB_HOST !== '127.0.0.1' || env.BFF_SESSION_DB_NAME !== 'scrapmart_bff_local_test' ||
        env.BFF_SESSION_DB_USER !== 'scrapmart_bff_runtime' || !Number.isInteger(port) || port < 1024 || port > 65535 ||
        !env.BFF_SESSION_DB_PASSWORD) throw new SessionError();
    const store = new SessionStore({ host: '127.0.0.1', port, database: 'scrapmart_bff_local_test',
      user: 'scrapmart_bff_runtime', password: env.BFF_SESSION_DB_PASSWORD,
    }, vault);
    return { store, close: () => store.close() };
  } catch { throw new SessionError(); }
}

export const browserSessionCookie = Object.freeze({
  name: '__Host-scrapmart_session', httpOnly: true, secure: true,
  sameSite: 'lax' as const, path: '/',
});
