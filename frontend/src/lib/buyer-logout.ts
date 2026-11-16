type LogoutResult = { status: "confirmed" | "already_signed_out" | "error"; message: string };
type Transport = (input: string, init: RequestInit) => Promise<Response>;

const unconfirmed = "We could not confirm sign-out. Retry to check your session.";

export function buyerLogoutDestination(result: LogoutResult): string | null {
  return result.status === "confirmed" || result.status === "already_signed_out" ? "/login?role=buyer" : null;
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
      if (response.status === 204) return { status: "confirmed", message: "Signed out." };
      if (response.status === 401) {
        const body: unknown = await response.json();
        if (body && typeof body === "object" && "detail" in body && body.detail &&
            typeof body.detail === "object" && "code" in body.detail && body.detail.code === "session_required") {
          const session = await transport("/api/auth/session", {
            method: "GET", credentials: "same-origin", cache: "no-store", redirect: "error",
          });
          if (session.status === 401) {
            const state: unknown = await session.json();
            if (state && typeof state === "object" && "detail" in state && state.detail &&
                typeof state.detail === "object" && "code" in state.detail && state.detail.code === "session_required") {
              return { status: "already_signed_out", message: "Your browser session is no longer active." };
            }
          }
        }
      }
      return { status: "error", message: unconfirmed };
    } catch {
      return { status: "error", message: unconfirmed };
    } finally {
      pending = false;
    }
  };
}
