type LogoutResult = { status: "confirmed" | "error"; message: string };
type Transport = (input: string, init: RequestInit) => Promise<Response>;

const unconfirmed = "We could not confirm sign-out. Your browser session may have been cleared; reload to check your account status.";

export function buyerLogoutDestination(result: LogoutResult): string | null {
  return result.status === "confirmed" ? "/login?role=buyer" : null;
}

export function createBuyerLogoutClient(transport: Transport = fetch) {
  let pending = false;
  return async function logout(): Promise<LogoutResult> {
    if (pending) return { status: "error", message: "Sign-out is already in progress." };
    pending = true;
    try {
      const response = await transport("/api/auth/logout", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
        headers: { "X-ScrapMart-CSRF": "1" },
      });
      return response.status === 204
        ? { status: "confirmed", message: "Signed out." }
        : { status: "error", message: unconfirmed };
    } catch {
      return { status: "error", message: unconfirmed };
    } finally {
      pending = false;
    }
  };
}
