// Node's native test runner does not implement Next.js's path aliases,
// extensionless TypeScript imports, or the "server-only" boundary marker.
// This loader is test-only: never use it for the app or production runtime.
export async function resolve(specifier, context, nextResolve) {
  // HTTP auth tests use an isolated PostgreSQL double, never a real socket.
  if (specifier === 'pg' && process.env.SCRAPMART_TEST_PG_DOUBLE === '1') {
    return { url: new URL('./session-pg-double.mjs', import.meta.url).href, shortCircuit: true };
  }
  if (specifier === 'server-only') {
    return { url: 'data:text/javascript,export%20%7B%7D', shortCircuit: true };
  }
  if (specifier.startsWith('@/')) {
    const mapped = new URL('../../src/' + specifier.slice(2), import.meta.url);
    for (const extension of ['.ts', '.tsx']) {
      try { return await nextResolve(mapped.href + extension, context); }
      catch (error) { if (error?.code !== 'ERR_MODULE_NOT_FOUND') throw error; }
    }
  }
  if (specifier.startsWith('.') && !/\.[cm]?[jt]sx?$/.test(specifier)) {
    for (const extension of ['.ts', '.tsx']) {
      try { return await nextResolve(specifier + extension, context); }
      catch (error) { if (error?.code !== 'ERR_MODULE_NOT_FOUND') throw error; }
    }
  }
  return nextResolve(specifier, context);
}
