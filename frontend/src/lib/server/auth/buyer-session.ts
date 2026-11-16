import 'server-only';
import { z } from 'zod';
import { handleAuthentication } from './runtime';

const session = z.object({
  authenticated: z.literal(true),
  capabilities: z.object({ buyer: z.literal(true) }).passthrough(),
  expires_at: z.iso.datetime({ offset: true }),
});
export type BuyerSessionDecision = 'allow' | 'login' | 'refresh' | 'unavailable';
export async function buyerSessionDecision(cookieHeader: string | null,
  handle: typeof handleAuthentication = handleAuthentication): Promise<BuyerSessionDecision> {
  if (!cookieHeader) return 'login';
  try {
    const response = await handle(new Request('https://session.check.invalid/api/auth/session', {
      method: 'GET', headers: { Cookie: cookieHeader }, cache: 'no-store', credentials: 'omit',
    }), ['session']);
    if (response.status === 401) {
      const body: unknown = await response.json();
      return typeof body === 'object' && body !== null && 'detail' in body &&
        typeof body.detail === 'object' && body.detail !== null && 'code' in body.detail &&
        body.detail.code === 'session_refresh_required' ? 'refresh' : 'login';
    }
    if (response.status !== 200) return 'unavailable';
    const parsed = session.safeParse(await response.json());
    return parsed.success && Date.parse(parsed.data.expires_at) > Date.now() ? 'allow' : 'login';
  } catch { return 'unavailable'; }
}
