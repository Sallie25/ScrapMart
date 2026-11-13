import { loginSchema, vendorSignupSchema } from "./validations/auth";
import type { LoginFormValues, SignupFormValues } from "./validations/auth";

type Result = { status: "accepted" | "authenticated" | "error"; message: string; fields?: string[] };
type Transport = (input: string, init: RequestInit) => Promise<Response>;
const unavailable = "Vendor authentication is unavailable. Please try again later.";
const accepted = "If registration was successful, you can now sign in.";
const safeFields = ["email", "password", "full_name", "phone_number", "business_name"];

async function interpret(response: Response, operation: "signup" | "login"): Promise<Result> {
  let body: unknown;
  try { body = await response.json(); } catch { return { status: "error", message: unavailable }; }
  if (body && typeof body === "object" && operation === "signup" && response.status === 202 &&
    "message" in body && body.message === accepted) return { status: "accepted", message: accepted };
  if (body && typeof body === "object" && operation === "login" && response.status === 200 &&
    "authenticated" in body && body.authenticated === true) return { status: "authenticated", message: "Signed in." };
  if (!body || typeof body !== "object" || !("detail" in body) || !body.detail ||
    typeof body.detail !== "object" || !("code" in body.detail)) return { status: "error", message: unavailable };
  const detail = body.detail as { code?: unknown; fields?: unknown };
  const fields = Array.isArray(detail.fields) ? detail.fields.filter((value): value is string =>
    typeof value === "string" && safeFields.includes(value)) : [];
  const message = detail.code === "validation_error" ? "Please check the highlighted fields." :
    detail.code === "invalid_credentials" ? "Email or password is incorrect." :
    detail.code === "logout_required" ? "Sign out of the current account first." :
    detail.code === "rate_limited" ? "Too many attempts. Please try later." : unavailable;
  return { status: "error", message, fields };
}

export function createVendorAuthClient(transport: Transport = fetch) {
  let pending = false;
  async function submit(operation: "signup" | "login", values: SignupFormValues | LoginFormValues): Promise<Result> {
    if (pending) return { status: "error", message: "A request is already in progress." };
    pending = true;
    try {
      const payload = operation === "signup" ? (() => {
        const value = vendorSignupSchema.parse(values);
        return { full_name: value.fullName, phone_number: value.phone || null,
          email: value.email, password: value.password, business_name: value.businessName };
      })() : (() => { const value = loginSchema.parse(values);
        return { email: value.email, password: value.password }; })();
      const response = await transport(`/api/auth/vendor/${operation}`, {
        method: "POST", credentials: "same-origin", cache: "no-store", redirect: "error",
        headers: { "Content-Type": "application/json", "X-ScrapMart-CSRF": "1" }, body: JSON.stringify(payload),
      });
      return await interpret(response, operation);
    } catch { return { status: "error", message: unavailable }; }
    finally { pending = false; }
  }
  return { signup: (values: SignupFormValues) => submit("signup", values),
    login: (values: LoginFormValues) => submit("login", values) };
}
