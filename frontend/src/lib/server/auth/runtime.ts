import 'server-only';
import { createBffHandlers } from './bff';

// Intentionally no environment switch, fetch transport, pool or secret loading.
// Enabling real dependencies requires a separately authorized integration batch.
export const handleAuthentication = createBffHandlers();
