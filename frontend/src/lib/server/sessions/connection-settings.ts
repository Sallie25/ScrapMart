import 'server-only';
import { isIP } from 'node:net';
import { X509Certificate } from 'node:crypto';
import { SessionError } from './crypto';

export type LocalSessionSettings = Readonly<{
  host: '127.0.0.1'; port: number; database: 'scrapmart_bff_local_test';
  user: 'scrapmart_bff_runtime'; password: string;
}>;
export type TlsSessionSettings = Readonly<{
  mode: 'tls'; environment: 'staging' | 'production'; host: string; port: number;
  database: string; user: 'scrapmart_bff_runtime'; password: string; ca?: string;
}>;
export type SessionConnectionSettings = LocalSessionSettings | TlsSessionSettings;

// DNS only: no socket paths, URLs, IP literals, short names or local aliases.
// DNS resolution and target ownership must be verified in controlled acceptance.
export function requireRuntimeHostname(host: string): void {
  if (typeof host !== 'string' || host.length > 253 || host !== host.toLowerCase() ||
      isIP(host) || /^[\d.]+$/.test(host) || !host.includes('.') ||
      host.split('.').some(label => !/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(label)) ||
      /(?:^|\.)(?:localhost|local|internal|home|invalid)$/.test(host)) throw new SessionError();
}

export function validateSessionSettings(settings: SessionConnectionSettings): void {
  if (!settings || ![Object.prototype, null].includes(Object.getPrototypeOf(settings))) throw new SessionError();
  const descriptors = Object.getOwnPropertyDescriptors(settings);
  // Check descriptors before reading ANY value; reject getters, symbols and extras.
  if (Reflect.ownKeys(settings).some(key => typeof key !== 'string') ||
      Object.values(descriptors).some(value => !('value' in value))) throw new SessionError();
  const tls = Object.hasOwn(descriptors, 'mode');
  const names = ['host', 'port', 'database', 'user', 'password', ...(tls ? ['mode', 'environment'] : [])];
  if (tls && Object.hasOwn(descriptors, 'ca')) names.push('ca');
  if (Object.keys(descriptors).length !== names.length || names.some(name => !Object.hasOwn(descriptors, name))) throw new SessionError();
  if (!Number.isInteger(settings.port) || settings.port < 1024 || settings.port > 65535 ||
      settings.user !== 'scrapmart_bff_runtime' || typeof settings.password !== 'string' || !settings.password) throw new SessionError();
  if (!tls) {
    if (settings.host !== '127.0.0.1' || settings.database !== 'scrapmart_bff_local_test') throw new SessionError();
    return;
  }
  const remote = settings as TlsSessionSettings;
  requireRuntimeHostname(remote.host);
  if (remote.mode !== 'tls' || !['staging', 'production'].includes(remote.environment) ||
      remote.database !== `scrapmart_bff_${remote.environment}` ||
      remote.password.length < 24 || remote.password.length > 1024 || /[\x00-\x20\x7f]/.test(remote.password)) throw new SessionError();
  if (remote.ca !== undefined) {
    if (typeof remote.ca !== 'string' || remote.ca.length > 65536) throw new SessionError();
    const certificates = remote.ca.match(/-----BEGIN CERTIFICATE-----[\s\S]*?-----END CERTIFICATE-----/g);
    if (!certificates?.length || remote.ca.replace(/-----BEGIN CERTIFICATE-----[\s\S]*?-----END CERTIFICATE-----/g, '').trim()) throw new SessionError();
    for (const pem of certificates) {
      const certificate = new X509Certificate(pem);
      if (!certificate.ca || Date.parse(certificate.validFrom) > Date.now() || Date.parse(certificate.validTo) <= Date.now()) throw new SessionError();
    }
  }
}
