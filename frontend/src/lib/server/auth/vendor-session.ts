import 'server-only';
import { z } from 'zod';
import { handleAuthentication } from './runtime';

const statusSchema = z.object({ verification_status: z.enum(['pending', 'approved', 'rejected', 'suspended']) });
export type VendorDecision = { kind: 'allow'; verificationStatus: z.infer<typeof statusSchema>['verification_status'] } |
  { kind: 'login' } | { kind: 'refresh' } | { kind: 'forbidden' } | { kind: 'unavailable' };

export async function vendorSessionDecision(cookieHeader: string | null,
  handle: typeof handleAuthentication = handleAuthentication): Promise<VendorDecision> {
  if (!cookieHeader) return { kind: 'login' };
  try {
    const response = await handle(new Request('https://session.check.invalid/api/auth/vendor/status', {
      method: 'GET', headers: { Cookie: cookieHeader }, cache: 'no-store', credentials: 'omit',
    }), ['vendor', 'status']);
    if (response.status === 401) {
      const body: unknown = await response.json();
      const code = body && typeof body === 'object' && 'detail' in body && body.detail &&
        typeof body.detail === 'object' && 'code' in body.detail ? body.detail.code : null;
      return { kind: code === 'session_refresh_required' ? 'refresh' : 'login' };
    }
    if (response.status === 403) return { kind: 'forbidden' };
    if (response.status !== 200) return { kind: 'unavailable' };
    const parsed = statusSchema.safeParse(await response.json());
    return parsed.success ? { kind: 'allow', verificationStatus: parsed.data.verification_status } : { kind: 'unavailable' };
  } catch { return { kind: 'unavailable' }; }
}
