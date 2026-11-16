import { createBuyerLogoutClient } from './buyer-logout';

export type AccountRole = 'buyer' | 'vendor';
type Transport = (input: string, init: RequestInit) => Promise<Response>;
export type LoginSession = { status: 'authenticated'; role: AccountRole } |
  { status: 'anonymous' } | { status: 'refresh_required' } | { status: 'unavailable' };
export type ResolvedLoginSession = Exclude<LoginSession, { status: 'refresh_required' }>;
export type SwitchResult = { status: 'signed_out' } | { status: 'error'; message: string };

const unavailable = 'We could not check your current session. Please try again.';

export function createLoginSessionClient(transport: Transport = fetch) {
  const logout = createBuyerLogoutClient(transport);
  async function check(preferredRole: AccountRole): Promise<LoginSession> {
    try {
      const response = await transport('/api/auth/session', {
        method: 'GET', credentials: 'same-origin', cache: 'no-store', redirect: 'error',
      });
      if (response.status === 401) {
        const body: unknown = await response.json();
        const code = body && typeof body === 'object' && 'detail' in body && body.detail &&
          typeof body.detail === 'object' && 'code' in body.detail ? body.detail.code : null;
        if (code === 'session_required') return { status: 'anonymous' };
        if (code === 'session_refresh_required') return { status: 'refresh_required' };
        return { status: 'unavailable' };
      }
      if (response.status !== 200) return { status: 'unavailable' };
      const data: unknown = await response.json();
      if (!data || typeof data !== 'object' || !('authenticated' in data) || data.authenticated !== true ||
          !('capabilities' in data) || !data.capabilities || typeof data.capabilities !== 'object') {
        return { status: 'unavailable' };
      }
      const capabilities = data.capabilities;
      if (!('buyer' in capabilities) || typeof capabilities.buyer !== 'boolean' ||
          !('vendor' in capabilities) || typeof capabilities.vendor !== 'boolean') {
        return { status: 'unavailable' };
      }
      if (capabilities[preferredRole]) return { status: 'authenticated', role: preferredRole };
      if (capabilities.buyer) return { status: 'authenticated', role: 'buyer' };
      if (capabilities.vendor) return { status: 'authenticated', role: 'vendor' };
      return { status: 'unavailable' };
    } catch { return { status: 'unavailable' }; }
  }
  async function resolveOnce(preferredRole: AccountRole): Promise<ResolvedLoginSession> {
    const initial = await check(preferredRole);
    if (initial.status !== 'refresh_required') return initial;
    try {
      const refreshed = await transport('/api/auth/refresh', {
        method: 'POST', credentials: 'same-origin', cache: 'no-store', redirect: 'error',
        headers: { 'X-ScrapMart-CSRF': '1' },
      });
      if (refreshed.status === 401) {
        const latest = await check(preferredRole);
        return latest.status === 'anonymous' ? latest : { status: 'unavailable' };
      }
      if (refreshed.status !== 200) return { status: 'unavailable' };
      const latest = await check(preferredRole);
      return latest.status === 'refresh_required' ? { status: 'unavailable' } : latest;
    } catch { return { status: 'unavailable' }; }
  }
  // React can replay mount effects. Share overlapping checks so an expiring
  // session never spends its single-use refresh credential twice.
  let resolving: Promise<ResolvedLoginSession> | undefined;
  function resolve(preferredRole: AccountRole): Promise<ResolvedLoginSession> {
    if (resolving) return resolving;
    resolving = resolveOnce(preferredRole).finally(() => { resolving = undefined; });
    return resolving;
  }
  async function switchAccount(preferredRole: AccountRole): Promise<SwitchResult> {
    const result = await logout();
    if (result.status === 'error') return { status: 'error', message: result.message };
    const current = await check(preferredRole);
    if (current.status === 'authenticated' || current.status === 'refresh_required') return {
      status: 'error', message: 'A session is still active. Reload before signing in with another account.',
    };
    if (current.status === 'unavailable') return { status: 'error', message: unavailable };
    return { status: 'signed_out' };
  }
  return { check, resolve, switchAccount };
}
