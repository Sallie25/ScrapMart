import 'server-only';
import { z } from 'zod';
import { acknowledgment, capabilities, vendorProfile, vendorOnboarding, tokenResponse } from './contracts';
import type { Role } from './contracts';
import type { Credentials } from '../sessions/crypto';

export const backendRefreshCookie = '__Secure-scrapmart_refresh';
export class BackendFailure extends Error {
  readonly status: number;
  readonly retryAfter?: string;
  readonly fields: string[];
  constructor(status = 503, retryAfter?: string, fields: string[] = []) {
    super('Authentication service unavailable'); this.name = 'BackendFailure';
    this.status = status; this.retryAfter = retryAfter; this.fields = fields;
  }
}
export type HttpTransport = (request: Request) => Promise<Response>;
export function exactHttpsOrigin(value: string): string {
  const url = new URL(value);
  if (url.protocol !== 'https:' || url.username || url.password || url.origin !== value) throw new BackendFailure();
  return url.origin;
}
export async function boundedJson(body: ReadableStream<Uint8Array> | null, signal?: AbortSignal): Promise<unknown> {
  if (!body) throw new BackendFailure(422);
  const reader = body.getReader(); const chunks: Uint8Array[] = []; let length = 0;
  const cancel = () => { void reader.cancel().catch(() => {}); };
  signal?.addEventListener('abort', cancel, { once: true });
  if (signal?.aborted) cancel();
  try {
    while (true) {
      const chunk = await reader.read(); if (chunk.done) break;
      length += chunk.value.byteLength;
      if (length > 16384) { void reader.cancel().catch(() => {}); throw new BackendFailure(413); }
      chunks.push(chunk.value);
    }
    if (signal?.aborted) throw new BackendFailure();
    const bytes = new Uint8Array(length); let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
    return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
  } catch (error) { if (error instanceof BackendFailure) throw error; throw new BackendFailure(422); }
  finally { signal?.removeEventListener('abort', cancel); reader.releaseLock(); }
}
function refreshCookie(headers: Headers): { value: string; expiresAt: Date } {
  const matching = headers.getSetCookie().filter(cookie => cookie.split('=', 1)[0].trim() === backendRefreshCookie);
  if (matching.length !== 1) throw new BackendFailure();
  if (matching[0].length > 2048) throw new BackendFailure();
  const [first, ...parts] = matching[0].split(';');
  const value = first.slice(first.indexOf('=') + 1);
  if (!/^[A-Za-z0-9_-]{43}$/.test(value) || Buffer.from(value, 'base64url').toString('base64url') !== value) throw new BackendFailure();
  const attrs: Record<string, string> = Object.create(null);
  for (const part of parts) {
    const [name, ...rest] = part.trim().split('='); const key = name.toLowerCase();
    if (Object.hasOwn(attrs, key)) throw new BackendFailure(); attrs[key] = rest.join('=');
  }
  if (attrs.secure !== '' || attrs.httponly !== '' || attrs.path !== '/api/v1/auth' ||
      attrs.samesite?.toLowerCase() !== 'lax' || Object.hasOwn(attrs, 'domain') ||
      !/^\d+$/.test(attrs['max-age'] ?? '') || !Number.isSafeInteger(Number(attrs['max-age'])) ||
      Number(attrs['max-age']) < 1 || Number(attrs['max-age']) > 2147483647) throw new BackendFailure();
  const expiresAt = new Date(attrs.expires);
  if (!Number.isFinite(expiresAt.getTime()) || expiresAt.getTime() <= Date.now()) throw new BackendFailure();
  return { value, expiresAt };
}

// No default fetch, global network transport or deployment configuration. Tests
// inject a synthetic transport; production wiring is deliberately disabled.
export class BackendAuthClient {
  #origin: string; #browserOrigin: string; #transport: HttpTransport; #timeout: number;
  constructor(options: { origin: string; browserOrigin: string; transport: HttpTransport; timeoutMs?: number }) {
    this.#origin = exactHttpsOrigin(options.origin); this.#browserOrigin = exactHttpsOrigin(options.browserOrigin);
    this.#transport = options.transport; this.#timeout = options.timeoutMs ?? 5000;
    if (typeof this.#transport !== 'function' || !Number.isInteger(this.#timeout) || this.#timeout < 1 || this.#timeout > 10000) throw new BackendFailure();
  }
  async #call<T>(path: string, method: 'GET' | 'POST' | 'PATCH', decode: (body: unknown, headers: Headers, started: number) => T,
    options: { body?: unknown; bearer?: string; cookie?: string } = {}): Promise<T> {
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout> | undefined;
    const started = Date.now();
    try {
      const headers = new Headers();
      if (method !== 'GET') { headers.set('Origin', this.#browserOrigin); headers.set('X-ScrapMart-CSRF', '1'); }
      if (options.body !== undefined) headers.set('Content-Type', 'application/json');
      if (options.bearer) headers.set('Authorization', `Bearer ${options.bearer}`);
      if (options.cookie) headers.set('Cookie', `${backendRefreshCookie}=${options.cookie}`);
      const request = new Request(this.#origin + '/api/v1/auth' + path, { method, headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: controller.signal, redirect: 'error', credentials: 'omit', cache: 'no-store' });
      return await Promise.race([
        (async () => {
          const response = await this.#transport(request);
          if (response.status === 204) {
            if (path !== '/logout' && path !== '/vendor/enroll' && path !== '/phone/verify-code' && path !== '/vendor/verification/submit' && !/^\\/verification\\/cases\\/[0-9a-f-]{36}\\/(approve|reject)$/i.test(path)) throw new BackendFailure();
            return decode(null, response.headers, started);
          }
          if (response.headers.get('content-type')?.split(';', 1)[0].trim().toLowerCase() !== 'application/json') throw new BackendFailure();
          let body: unknown;
          try { body = await boundedJson(response.body, controller.signal); } catch { throw new BackendFailure(); }
          if (response.status < 200 || response.status >= 300) {
            const error = z.object({ detail: z.object({ fields: z.array(z.string()).max(5).optional() }).passthrough() }).safeParse(body);
            const fields = error.success ? error.data.detail.fields ?? [] : [];
            const retry = response.headers.get('retry-after');
            throw new BackendFailure([400,401,403,409,413,415,422,429,503].includes(response.status) ? response.status : 502,
              retry && /^\d{1,5}$/.test(retry) ? retry : undefined, fields);
          }
          if (response.status !== ((path === '/logout' || path === '/vendor/enroll' || path === '/phone/verify-code' || path === '/vendor/verification/submit') ? 204 : (path.endsWith('/signup') || path === '/phone/send-code') ? 202 : 200)) throw new BackendFailure();
          return decode(body, response.headers, started);
        })(),
        new Promise<never>((_, reject) => { timer = setTimeout(() => { controller.abort(); reject(new BackendFailure()); }, this.#timeout); }),
      ]);
    } catch (error) { if (error instanceof BackendFailure) throw error; throw new BackendFailure(); }
    finally { if (timer) clearTimeout(timer); controller.abort(); }
  }
  register(role: Role, body: unknown): Promise<void> {
    return this.#call(`/${role}/signup`, 'POST', value => {
      if (!z.object({ message: z.literal(acknowledgment) }).strict().safeParse(value).success) throw new BackendFailure();
    }, { body });
  }
  #credentials(body: unknown, headers: Headers, started: number): { credentials: Credentials; expiresAt: Date } {
    const parsed = tokenResponse.safeParse(body); if (!parsed.success) throw new BackendFailure();
    const cookie = refreshCookie(headers);
    return { credentials: { accessToken: parsed.data.access_token, refreshCookie: cookie.value,
      accessExpiresAt: new Date(started + parsed.data.expires_in * 1000).toISOString() }, expiresAt: cookie.expiresAt };
  }
  login(role: Role, body: unknown) {
    return this.#call(`/${role}/login`, 'POST', (value, headers, started) => this.#credentials(value, headers, started), { body });
  }
  refresh(cookie: string) {
    return this.#call('/refresh', 'POST', (value, headers, started) => this.#credentials(value, headers, started), { cookie });
  }
  logout(cookie: string): Promise<void> {
    return this.#call('/logout', 'POST', value => { if (value !== null) throw new BackendFailure(); }, { cookie });
  }
  enrollVendor(bearer: string, body: { business_name: string; current_password: string }): Promise<void> {
    return this.#call('/vendor/enroll', 'POST', value => {
      if (value !== null) throw new BackendFailure();
    }, { bearer, body });
  }
  async uploadIdentityDocument(bearer: string, kind: string, bytes: Uint8Array, mediaType: string): Promise<void> {
    if (!['national_id', 'passport', 'drivers_license', 'voter_id'].includes(kind) ||
        !['image/jpeg', 'image/png'].includes(mediaType) ||
        bytes.byteLength < 1 || bytes.byteLength > 3 * 1024 * 1024) throw new BackendFailure(422);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const headers = new Headers({
        Origin: this.#browserOrigin, 'X-ScrapMart-CSRF': '1',
        'Content-Type': mediaType, Authorization: `Bearer ${bearer}`,
      });
      const request = new Request(
        this.#origin + '/api/v1/auth/vendor/identity-document?identification_type=' + encodeURIComponent(kind),
        { method: 'POST', headers, body: Buffer.from(bytes), signal: controller.signal,
          redirect: 'error', credentials: 'omit', cache: 'no-store' },
      );
      const result = await this.#transport(request);
      if (result.status === 200 || result.status === 201 || result.status === 204) {
        await result.body?.cancel();
        return;
      }
      await result.body?.cancel();
      throw new BackendFailure([400,401,403,413,415,422,429,503].includes(result.status) ? result.status : 502);
    } catch (error) {
      if (error instanceof BackendFailure) throw error;
      throw new BackendFailure();
    } finally { clearTimeout(timeout); controller.abort(); }
  }
  async decideVerificationCase(bearer: string, id: string, action: 'approve' | 'reject',
    payload: { expected_version: number; expected_evidence_revision: string; reason: string }): Promise<void> {
    // Decisions are never made by the BFF. Only the restricted backend reviewer
    // service may commit a version-checked audit event.
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(id) ||
        !Number.isSafeInteger(payload.expected_version) || payload.expected_version < 0 ||
        !payload.expected_evidence_revision || payload.expected_evidence_revision.length > 256 ||
        !payload.reason.trim() || payload.reason.length > 500)
      throw new BackendFailure(422);
    const path = '/verification/cases/' + encodeURIComponent(id) + '/' + action;
    return this.#call(path, 'POST', value => {
      if (value !== null && (typeof value !== 'object' || Array.isArray(value))) throw new BackendFailure();
    }, { bearer, body: payload });
  }
  reviewCases(bearer: string, status: 'pending' | 'approved' | 'rejected' | 'suspended', limit: number) {
    return this.#call('/verification/cases?status=' + status + '&limit=' + limit, 'GET', value => {
      if (!value || typeof value !== 'object' || Array.isArray(value)) throw new BackendFailure();
      return value;
    }, { bearer });
  }
  reviewCase(bearer: string, id: string) {
    return this.#call('/verification/cases/' + encodeURIComponent(id), 'GET', value => {
      if (!value || typeof value !== 'object' || Array.isArray(value)) throw new BackendFailure();
      return value;
    }, { bearer });
  }
  submitVendorVerification(bearer: string): Promise<void> {
    return this.#call('/vendor/verification/submit', 'POST', value => {
      if (value !== null && (typeof value !== 'object' || Array.isArray(value))) throw new BackendFailure();
    }, { bearer, body: {} });
  }
  sendPhoneVerificationCode(bearer: string): Promise<void> {
    return this.#call('/phone/send-code', 'POST', () => undefined, { bearer, body: {} });
  }
  verifyPhoneCode(bearer: string, code: string): Promise<void> {
    return this.#call('/phone/verify-code', 'POST', value => {
      if (value !== null) throw new BackendFailure();
    }, { bearer, body: { code } });
  }
  getVendorOnboarding(bearer: string) {
    return this.#call('/vendor/onboarding', 'GET', value => {
      const parsed = vendorOnboarding.safeParse(value);
      if (!parsed.success) throw new BackendFailure();
      return parsed.data;
    }, { bearer });
  }
  updateVendorOnboarding(bearer: string, body: {
    business_name?: string; shop_location?: string; shop_address?: string
  }) {
    return this.#call('/vendor/onboarding', 'PATCH', value => {
      const parsed = vendorOnboarding.safeParse(value);
      if (!parsed.success) throw new BackendFailure();
      return parsed.data;
    }, { bearer, body });
  }
  capabilities(bearer: string) {
    return this.#call('/capabilities', 'GET', value => {
      const parsed = capabilities.safeParse(value); if (!parsed.success) throw new BackendFailure(); return parsed.data;
    }, { bearer });
  }
  vendorStatus(bearer: string) {
    return this.#call('/vendor/me', 'GET', value => {
      const parsed = vendorProfile.safeParse(value); if (!parsed.success) throw new BackendFailure();
      return { verification_status: parsed.data.verification_status };
    }, { bearer });
  }
}
