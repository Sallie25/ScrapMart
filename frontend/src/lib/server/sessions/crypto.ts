import 'server-only';
import { createCipheriv, createDecipheriv, createHash, randomBytes } from 'node:crypto';

export class SessionError extends Error {
  constructor() { super('Session operation unavailable'); this.name = 'SessionError'; }
}

export function newIdentifier(): string { return randomBytes(32).toString('base64url'); }
export function hashIdentifier(value: string): string {
  if (!/^[A-Za-z0-9_-]{43}$/.test(value) || Buffer.from(value, 'base64url').toString('base64url') !== value) throw new SessionError();
  return createHash('sha256').update(value).digest('hex');
}

export type Credentials = { accessToken: string; refreshCookie: string; accessExpiresAt: string };
export type Envelope = { version: string; nonce: string; ciphertext: string; tag: string };

export function validateCredentials(value: Credentials): void {
  if (!value || typeof value.accessToken !== 'string' || !value.accessToken.length || value.accessToken.length > 16384 ||
      /[\r\n\x00]/.test(value.accessToken) || !/^[A-Za-z0-9_-]{43}$/.test(value.refreshCookie) ||
      Buffer.from(value.refreshCookie, 'base64url').toString('base64url') !== value.refreshCookie ||
      !Number.isFinite(Date.parse(value.accessExpiresAt))) throw new SessionError();
}

// Private fields keep incidental JSON serialization from disclosing credentials or keys.
export class CredentialVault {
  #keys: Readonly<Record<string, Buffer>>;
  #current: string;
  constructor(current: string, keys: Readonly<Record<string, Buffer>>) {
    if (!/^[A-Za-z0-9_-]{1,32}$/.test(current) || !Object.hasOwn(keys, current) ||
        Object.entries(keys).some(([v, k]) => !/^[A-Za-z0-9_-]{1,32}$/.test(v) || k.length !== 32)) throw new SessionError();
    this.#current = current;
    this.#keys = Object.fromEntries(Object.entries(keys).map(([v, k]) => [v, Buffer.from(k)]));
  }
  seal(hash: string, credentials: Credentials): Envelope {
    try {
      validateCredentials(credentials);
      const nonce = randomBytes(12);
      const cipher = createCipheriv('aes-256-gcm', this.#keys[this.#current], nonce);
      cipher.setAAD(Buffer.from(`scrapmart:bff:1:${hash}:${this.#current}`));
      const ciphertext = Buffer.concat([cipher.update(JSON.stringify(credentials), 'utf8'), cipher.final()]);
      return { version: this.#current, nonce: nonce.toString('base64'), ciphertext: ciphertext.toString('base64'), tag: cipher.getAuthTag().toString('base64') };
    } catch { throw new SessionError(); }
  }
  open(hash: string, envelope: Envelope): Credentials {
    try {
      if (!Object.hasOwn(this.#keys, envelope.version)) throw new SessionError();
      const nonce = Buffer.from(envelope.nonce, 'base64');
      const tag = Buffer.from(envelope.tag, 'base64');
      if (nonce.length !== 12 || tag.length !== 16) throw new SessionError();
      const decipher = createDecipheriv('aes-256-gcm', this.#keys[envelope.version], nonce);
      decipher.setAAD(Buffer.from(`scrapmart:bff:1:${hash}:${envelope.version}`));
      decipher.setAuthTag(tag);
      const value = JSON.parse(Buffer.concat([decipher.update(Buffer.from(envelope.ciphertext, 'base64')), decipher.final()]).toString('utf8')) as Credentials;
      validateCredentials(value);
      return value;
    } catch { throw new SessionError(); }
  }
}
