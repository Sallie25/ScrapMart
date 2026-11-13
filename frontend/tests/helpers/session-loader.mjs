// Explicit test-only server marker and driver substitutions. Production retains
// import 'server-only' and real pg; no production module imports this loader.
import { registerHooks } from 'node:module';
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier === 'server-only') return { url: 'data:text/javascript,export{}', shortCircuit: true };
    if (specifier === 'pg' && context.parentURL?.endsWith('/src/lib/server/sessions/database.ts')) {
      const driver = process.env.SCRAPMART_BFF_ISOLATED_TEST === '1' ? './postgres-pg-faults.mjs' : './session-pg-double.mjs';
      return { url: new URL(driver, import.meta.url).href, shortCircuit: true };
    }
    if ((/\/src\/lib\/server\/(sessions|auth|vendor)\//.test(context.parentURL ?? '') ||
        context.parentURL?.includes('/src/app/api/auth/') || context.parentURL?.includes('/src/app/api/vendor/')) &&
        specifier.startsWith('.') && !/\.[a-z]+$/.test(specifier)) {
      return nextResolve(`${specifier}.ts`, context);
    }
    return nextResolve(specifier, context);
  },
});
