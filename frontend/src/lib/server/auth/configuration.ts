import 'server-only';
import { CredentialVault } from '../sessions/crypto';
import { validateSessionSettings, requireRuntimeHostname } from '../sessions/connection-settings';
import type { TlsSessionSettings } from '../sessions/connection-settings';
import { SessionStore } from '../sessions/store';
import { BackendAuthClient, exactHttpsOrigin } from './backend';
import type { HttpTransport } from './backend';
import { createBffHandlers } from './bff';
import { createVendorHandlers } from '../vendor/handlers';

export class RuntimeConfigurationError extends Error {
  constructor() { super('Authentication runtime configuration is invalid'); this.name = 'RuntimeConfigurationError'; }
}
function required(env: NodeJS.ProcessEnv, name: string): string {
  const value = env[name];
  if (typeof value !== 'string' || !value || value !== value.trim()) throw new RuntimeConfigurationError();
  return value;
}
function origin(env: NodeJS.ProcessEnv, name: string): string {
  const value = exactHttpsOrigin(required(env, name));
  const url = new URL(value);
  requireRuntimeHostname(url.hostname);
  if (url.port) throw new RuntimeConfigurationError(); // Deployment HTTPS uses 443 only.
  return value;
}

// Validated secrets stay in private fields, never in a serializable config DTO.
// Construction validates synchronously, with no Pool, fetch, DNS or SQL activity.
export class AuthenticationRuntimeConfiguration {
  #settings?: TlsSessionSettings;
  #vault?: CredentialVault;
  #backendOrigin?: string;
  #browserOrigin?: string;
  get enabled(): boolean { return this.#settings !== undefined; }
  constructor(env: NodeJS.ProcessEnv) {
    try {
      const gate = env.BFF_AUTH_ENABLED;
      if (gate === undefined || gate === 'false') return;
      if (gate !== 'true' || env.NODE_TLS_REJECT_UNAUTHORIZED === '0' || process.env.NODE_TLS_REJECT_UNAUTHORIZED === '0') throw new RuntimeConfigurationError();
      const environment = required(env, 'BFF_AUTH_ENVIRONMENT');
      if (environment !== 'staging' && environment !== 'production') throw new RuntimeConfigurationError();
      const port = required(env, 'BFF_SESSION_DB_PORT');
      if (!/^[1-9]\d{3,4}$/.test(port)) throw new RuntimeConfigurationError();
      const ca = env.BFF_SESSION_DB_CA_PEM;
      const settings: TlsSessionSettings = { mode: 'tls', environment,
        host: required(env, 'BFF_SESSION_DB_HOST'), port: Number(port),
        database: required(env, 'BFF_SESSION_DB_NAME'),
        user: required(env, 'BFF_SESSION_DB_USER') as 'scrapmart_bff_runtime',
        password: required(env, 'BFF_SESSION_DB_PASSWORD'), ...(ca !== undefined ? { ca } : {}) };
      validateSessionSettings(settings);
      const backendOrigin = origin(env, 'BFF_BACKEND_ORIGIN');
      const browserOrigin = origin(env, 'BFF_BROWSER_ORIGIN');
      if (backendOrigin === browserOrigin) throw new RuntimeConfigurationError();
      const current = required(env, 'BFF_SESSION_KEY_VERSION');
      const serialized = required(env, 'BFF_SESSION_KEYS_JSON');
      if (serialized.length > 8192) throw new RuntimeConfigurationError();
      const encoded: unknown = JSON.parse(serialized);
      if (!encoded || Array.isArray(encoded) || typeof encoded !== 'object') throw new RuntimeConfigurationError();
      const entries = Object.entries(encoded);
      if (!entries.length || entries.length > 8) throw new RuntimeConfigurationError();
      const seen = new Set<string>();
      const keys = Object.fromEntries(entries.map(([version, value]) => {
        if (typeof value !== 'string') throw new RuntimeConfigurationError();
        const key = Buffer.from(value, 'base64');
        if (key.length !== 32 || key.toString('base64') !== value || new Set(key).size < 16 || seen.has(value)) throw new RuntimeConfigurationError();
        seen.add(value); return [version, key];
      }));
      const vault = new CredentialVault(current, keys);
      this.#settings = Object.freeze(settings); this.#vault = vault;
      this.#backendOrigin = backendOrigin; this.#browserOrigin = browserOrigin;
    } catch { throw new RuntimeConfigurationError(); }
  }
  // Explicit bootstrap only. Pool construction is lazy with respect to network;
  // neither creating the runtime nor closing it executes SQL or connects.
  createRuntime(transport?: HttpTransport) {
    if (!this.enabled) return { handle: createBffHandlers(), handleVendor: createVendorHandlers(), close: async () => {} };
    if (typeof transport !== 'function') throw new RuntimeConfigurationError();
    try {
      const backend = new BackendAuthClient({ origin: this.#backendOrigin!, browserOrigin: this.#browserOrigin!, transport });
      const store = new SessionStore(this.#settings!, this.#vault!);
      return { handle: createBffHandlers({ backend, store, browserOrigin: this.#browserOrigin! }),
        handleVendor: createVendorHandlers({ store, backendOrigin: this.#backendOrigin!, browserOrigin: this.#browserOrigin!, transport }),
        close: () => store.close() };
    } catch { throw new RuntimeConfigurationError(); }
  }
}
