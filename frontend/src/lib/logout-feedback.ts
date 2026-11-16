export type LogoutRole = 'buyer' | 'vendor';
const key = 'scrapmart:confirmed-signout';

// This marker carries no session data. It is written only after HTTP 204 and
// consumed once by the login page so the confirmation survives navigation.
export function markConfirmedLogout(role: LogoutRole, storage: Storage = sessionStorage): void {
  try { storage.setItem(key, role); } catch { /* Navigation still works if storage is unavailable. */ }
}

export function takeConfirmedLogout(role: LogoutRole, storage: Storage = sessionStorage): boolean {
  try {
    const value = storage.getItem(key);
    storage.removeItem(key);
    return value === role;
  } catch { return false; }
}
