import { handleVendorApi } from '@/lib/server/auth/runtime';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
type Context = { params: Promise<{ operation: string[] }> };
const handle = async (request: Request, context: Context) => handleVendorApi(request, (await context.params).operation);
export const GET = handle;
export const POST = handle;
export const PATCH = handle;
export const DELETE = handle;
