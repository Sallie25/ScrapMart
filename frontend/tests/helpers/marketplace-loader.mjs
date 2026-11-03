// Isolated offline tests retain the production server-only boundary.
import { registerHooks } from 'node:module';
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier === 'server-only') return { url: 'data:text/javascript,export{}', shortCircuit: true };
    if (/\/src\/lib\/(server\/)?marketplace\//.test(context.parentURL ?? '') && specifier.startsWith('.') && !/\.[a-z]+$/.test(specifier)) {
      return nextResolve(`${specifier}.ts`, context);
    }
    return nextResolve(specifier, context);
  },
});
// An accidentally omitted transport must never reach a network.
globalThis.fetch = async () => { throw new Error('Network forbidden in marketplace tests'); };
