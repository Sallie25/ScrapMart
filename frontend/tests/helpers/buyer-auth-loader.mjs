import { registerHooks } from 'node:module';
registerHooks({ resolve(specifier, context, nextResolve) {
  if ((context.parentURL?.endsWith('/src/lib/buyer-auth.ts') || context.parentURL?.endsWith('/src/lib/vendor-auth.ts')) && specifier === './validations/auth')
    return nextResolve('./validations/auth.ts', context);
  return nextResolve(specifier, context);
} });
