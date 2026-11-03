import 'server-only';
import { createBffHandlers } from './bff';

// Deployment preparation is available through AuthenticationRuntimeConfiguration.
// This route deliberately stays unwired: no ambient environment can activate it.
// A future authorized bootstrap must validate config, inject transport and own shutdown.
export const handleAuthentication = createBffHandlers();
