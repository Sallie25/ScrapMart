import { handleAuthentication } from '../../../../lib/server/auth/runtime';
import { authError } from '../../../../lib/server/auth/bff';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
type Context = { params: Promise<{ operation: string[] }> };
export async function GET(request: Request, context: Context) {
  return handleAuthentication(request, (await context.params).operation);
}
export async function POST(request: Request, context: Context) {
  return handleAuthentication(request, (await context.params).operation);
}
const denied = () => authError(405, 'method_not_allowed');
export const OPTIONS = denied;
export const PUT = denied;
export const PATCH = denied;
export const DELETE = denied;
export const HEAD = () => new Response(null, { status: 405, headers: { 'Cache-Control': 'no-store' } });
