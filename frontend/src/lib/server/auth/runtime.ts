import 'server-only';
import { AuthenticationRuntimeConfiguration } from './configuration';
import { authError } from './bff';
import type { HttpTransport } from './backend';

// Constructed only on first request. An omitted gate never reads secrets or creates a pool.
export function createAuthenticationBootstrap(env: NodeJS.ProcessEnv, transport: HttpTransport) {
  const configuration = new AuthenticationRuntimeConfiguration(env);
  const runtime = configuration.createRuntime(transport);
  let closed = false;
  return {
    enabled: configuration.enabled,
    handle(request: Request, operation: readonly string[]) {
      return closed ? Promise.resolve(authError(503, 'session_unavailable')) : runtime.handle(request, operation);
    },
    async close() {
      if (closed) return;
      closed = true;
      await runtime.close();
    },
  };
}

type Bootstrap = ReturnType<typeof createAuthenticationBootstrap>;
let active: Bootstrap | undefined;
function current(): Bootstrap {
  active ??= createAuthenticationBootstrap(process.env, request => fetch(request));
  return active;
}
export async function handleAuthentication(request: Request, operation: readonly string[]): Promise<Response> {
  try { return await current().handle(request, operation); }
  catch { return authError(503, 'session_unavailable'); }
}
export async function closeAuthenticationRuntime(): Promise<void> {
  const closing = active;
  active = undefined;
  await closing?.close();
}
