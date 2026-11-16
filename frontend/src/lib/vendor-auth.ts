import { vendorSignupSchema } from "./validations/auth";
import type { VendorSignupValues } from "./validations/auth";

type Result = { status: "accepted" | "error"; message: string; fields?: string[] };
type Transport = (input: string, init: RequestInit) => Promise<Response>;
const acknowledgment = "If registration was successful, you can now sign in.";
const unavailable = "Vendor registration is currently unavailable. Please try again later.";
const safeFields = new Set(["email", "password", "full_name", "phone_number", "business_name"]);

export function createVendorAuthClient(transport: Transport = fetch) {
  let pending = false;
  return {
    async signup(values: VendorSignupValues): Promise<Result> {
      if (pending) return { status: "error", message: "A request is already in progress." };
      pending = true;
      try {
        const parsed = vendorSignupSchema.parse(values);
        const response = await transport("/api/auth/vendor/signup", {
          method: "POST",
          credentials: "same-origin",
          cache: "no-store",
          redirect: "error",
          headers: { "Content-Type": "application/json", "X-ScrapMart-CSRF": "1" },
          body: JSON.stringify({
            full_name: parsed.fullName,
            email: parsed.email,
            phone_number: parsed.phone || null,
            password: parsed.password,
            business_name: parsed.businessName,
          }),
        });
        const body: unknown = await response.json();
        if (response.status === 202 && typeof body === "object" && body !== null &&
            "message" in body && body.message === acknowledgment)
          return { status: "accepted", message: acknowledgment };
        if (typeof body !== "object" || body === null || !("detail" in body) ||
            typeof body.detail !== "object" || body.detail === null ||
            !("code" in body.detail) || typeof body.detail.code !== "string")
          return { status: "error", message: unavailable };
        const detail = body.detail;
        const fields = "fields" in detail && Array.isArray(detail.fields)
          ? detail.fields.filter((field): field is string => typeof field === "string" && safeFields.has(field))
          : [];
        if (detail.code === "validation_error")
          return { status: "error", message: "Please check the highlighted fields and try again.", fields };
        if (detail.code === "rate_limited")
          return { status: "error", message: "Too many attempts. Please try again later." };
        if (detail.code === "authentication_disabled")
          return { status: "error", message: "Authentication is not activated yet. No account was created." };
        return { status: "error", message: unavailable };
      } catch {
        return { status: "error", message: unavailable };
      } finally {
        pending = false;
      }
    },
  };
}
