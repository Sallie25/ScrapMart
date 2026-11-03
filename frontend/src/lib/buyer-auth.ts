import { buyerSignupSchema, loginSchema } from "./validations/auth";
import type { BuyerSignupValues, LoginFormValues } from "./validations/auth";

type AuthResult = { status: "accepted" | "authenticated" | "error"; message: string; fields?: string[] };
type Transport = (input: string, init: RequestInit) => Promise<Response>;
const acknowledgment = "If registration was successful, you can now sign in.";
const unavailable = "Authentication is not available yet. Please try again later.";
const safeFields = ["email", "password", "full_name", "phone_number"];
const failed = (message: string, fields?: string[]): AuthResult => ({ status: "error", message, fields });

async function interpret(response: Response, operation: "signup" | "login"): Promise<AuthResult> {
  let body: unknown;
  try { body = await response.json(); } catch { return failed(unavailable); }
  if (operation === "signup" && response.status === 202 &&
    typeof body === "object" && body !== null && "message" in body && body.message === acknowledgment) {
    return { status: "accepted", message: acknowledgment };
  }
  if (operation === "login" && response.status === 200 &&
    typeof body === "object" && body !== null && "authenticated" in body && body.authenticated === true) {
    return { status: "authenticated", message: "Signed in." };
  }
  if (typeof body !== "object" || body === null || !("detail" in body) ||
    typeof body.detail !== "object" || body.detail === null || !("code" in body.detail) || typeof body.detail.code !== "string") return failed(unavailable);
  const code = body.detail.code;
  const fields = "fields" in body.detail && Array.isArray(body.detail.fields)
    ? body.detail.fields.filter((field): field is string => typeof field === "string" && safeFields.includes(field)) : [];
  if (code === "validation_error") return failed("Please check the highlighted fields and try again.", fields);
  if (code === "invalid_credentials") return failed("Email or password is incorrect.");
  if (code === "logout_required") return failed("Sign out of the current account before signing in again.");
  if (code === "rate_limited") return failed("Too many attempts. Please try again later.");
  if (code === "authentication_disabled") return failed("Authentication is not activated yet. No account or session was created.");
  return failed(unavailable);
}

export function buyerLoginDestination(result: AuthResult): string | null {
  return result.status === "authenticated" ? "/buyer/dashboard" : null;
}

export function createBuyerAuthClient(transport: Transport = fetch) {
  let pending = false;
  async function submit(operation: "signup" | "login", values: BuyerSignupValues | LoginFormValues): Promise<AuthResult> {
    if (pending) return failed("A request is already in progress.");
    pending = true;
    try {
      const payload = operation === "signup" ? (() => {
        const parsed = buyerSignupSchema.parse(values);
        return { full_name: parsed.fullName, phone_number: parsed.phone || null, email: parsed.email, password: parsed.password };
      })() : (() => {
        const parsed = loginSchema.parse(values);
        return { email: parsed.email, password: parsed.password };
      })();
      const response = await transport(`/api/auth/buyer/${operation}`, {
        method: "POST", credentials: "same-origin", cache: "no-store", redirect: "error",
        headers: { "Content-Type": "application/json", "X-ScrapMart-CSRF": "1" },
        body: JSON.stringify(payload),
      });
      return await interpret(response, operation);
    } catch { return failed(unavailable); }
    finally { pending = false; }
  }
  return { signup: (values: BuyerSignupValues) => submit("signup", values), login: (values: LoginFormValues) => submit("login", values) };
}
