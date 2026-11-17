"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { createBuyerAuthClient } from "@/lib/buyer-auth";
import { createVendorAuthClient } from "@/lib/vendor-auth";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { AuthField } from "@/components/auth/auth-field";
import {
  buyerSignupSchema,
  vendorSignupSchema,
  type SignupFormValues,
} from "@/lib/validations/auth";

const buyerFormSchema = buyerSignupSchema.extend({ previewConsent: z.boolean().refine(Boolean, "Confirm the registration acknowledgement") });

export function SignupForm({ role }: { role: "buyer" | "vendor" }) {
  const vendor = role === "vendor";
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<{ message: string; accepted: boolean } | null>(null);
  const inFlight = useRef(false);
  const client = useRef(createBuyerAuthClient());
  const vendorClient = useRef(createVendorAuthClient());
  const [showPassword, setShowPassword] = useState(false);
  const form = useForm<SignupFormValues>({
    resolver: zodResolver(vendor ? vendorSignupSchema.extend({ previewConsent: z.boolean().refine(Boolean, "Confirm the registration acknowledgement") }) : buyerFormSchema),
    defaultValues: {
      fullName: "",
      phone: "",
      email: "",
      password: "",
      previewConsent: false,
      ...(vendor
        ? { businessName: "" }
        : {}),
    },
  });
  const { register, handleSubmit, getFieldState, formState } = form;
  const submitSignup = async (values: SignupFormValues) => {
    if (inFlight.current) return;
    inFlight.current = true; setPending(true); setResult(null);
    try {
      const outcome = await (vendor ? vendorClient.current.signup(values) : client.current.signup(values));
      if (outcome.status === "accepted") form.resetField("password");
      else for (const field of outcome.fields ?? []) {
        const name = { full_name: "fullName", phone_number: "phone", email: "email", password: "password", business_name: "businessName" }[field] as "fullName" | "phone" | "email" | "password" | "businessName" | undefined;
        if (name) form.setError(name, { message: `Check ${name === "fullName" ? "full name" : name === "phone" ? "phone number" : name}.` });
      }
      setResult({ message: outcome.message, accepted: outcome.status === "accepted" });
    } finally { inFlight.current = false; setPending(false); }
  };
  const fieldError = (name: Parameters<typeof getFieldState>[0]) =>
    getFieldState(name, formState).error?.message;
  return (
    <form
      onChange={() => setResult(null)}
      onSubmit={event => { void handleSubmit(submitSignup)(event); }}
      className="mt-7"
      noValidate
    >
      <p
        className={`auth-muted mb-5 text-xs leading-relaxed ${vendor ? "sr-only" : ""}`}
      >
        Submit your details through ScrapMart authentication. Registration may be unavailable until the service is activated.
      </p>
      <div className="grid gap-4 md:grid-cols-2">
        <AuthField
          id="signup-full-name"
          label="Full name"
          placeholder="e.g. Tunde Adeyemi"
          autoComplete="name"
          required
          error={fieldError("fullName")}
          {...register("fullName")}
        />
        <AuthField
          id="signup-phone"
          label="Phone number"
          type="tel"
          placeholder="0801 234 5678"
          autoComplete="tel"
          required
          error={fieldError("phone")}
          {...register("phone")}
        />
        <AuthField
          id="signup-email"
          label="Email"
          type="email"
          placeholder="name@example.com"
          autoComplete="email"
          required
          error={fieldError("email")}
          {...register("email")}
        />
        <div>
          <div className="flex items-start gap-2">
            <div className="min-w-0 flex-1">
              <AuthField
                id="signup-password"
                label="Password"
                type={showPassword ? "text" : "password"}
                placeholder="15–128 characters"
                autoComplete="new-password"
                required
                helper={
                  vendor
                    ? "15–128 characters; Unicode and spaces allowed."
                    : "15–128 characters. Unicode and spaces are allowed; not only whitespace. No null characters or invalid Unicode text."
                }
                error={fieldError("password")}
                {...register("password")}
              />
            </div>
            <button
              type="button"
              className="auth-password-toggle mt-6"
              aria-label={showPassword ? "Hide password" : "Show password"}
              aria-pressed={showPassword}
              onClick={() => setShowPassword(!showPassword)}
            >
              {showPassword ? "Hide" : "Show"}
            </button>
          </div>
        </div>
        {vendor && (
          <>
            <AuthField
              id="signup-business-name"
              label="Shop / business name"
              placeholder="e.g. Akin Auto Parts"
              autoComplete="organization"
              required
              error={fieldError("businessName")}
              {...register("businessName")}
            />
          </>
        )}
      </div>
      <p
        className={`auth-helper mt-4 text-xs leading-relaxed ${vendor ? "sr-only" : ""}`}
      >
        Passwords are checked against the backend signup rules without trimming
        or changing them. Your password is sent only to the same-origin authentication route.
      </p>
      {vendor && (
        <p
          id="identity-demo"
          className="auth-helper mt-3 text-xs leading-relaxed"
        >
          Identity review remains required before a Vendor may publish listings.
          Shop location and address are completed after sign-in.
        </p>
      )}
      <label className="auth-muted mt-5 flex cursor-pointer items-start gap-3 text-sm font-medium">
        <input
          type="checkbox"
          className="mt-0.5 size-5 shrink-0"
          aria-invalid={Boolean(fieldError("previewConsent"))}
          aria-describedby={
            fieldError("previewConsent")
              ? "preview-consent-error"
              : "preview-terms"
          }
          {...register("previewConsent")}
        />
        <span>
          I understand registration is only confirmed by the authentication service.
        </span>
      </label>
      {fieldError("previewConsent") && (
        <p
          id="preview-consent-error"
          role="alert"
          className="mt-2 text-sm text-red-700"
        >
          {fieldError("previewConsent")}
        </p>
      )}
      <p
        id="preview-terms"
        className={`auth-helper mt-2 text-xs ${vendor ? "sr-only" : ""}`}
      >
        Terms and Privacy Policy pages are not available yet.
      </p>
      <Button type="submit" block className="auth-button mt-6" disabled={pending} loading={pending}>
        {pending ? "Submitting…" : vendor ? "Create vendor account" : "Create buyer account"}
      </Button>
      {result && <section role={result.accepted ? "status" : "alert"} className="auth-status mt-5">
        {result.accepted ? <>
          <p className="font-bold">Registration request received!</p>
          <p className="mt-2">You can now try logging in to ScrapMart.</p>
          <Link href={`/login?role=${role}`} className="auth-button mt-4 inline-flex min-h-12 items-center justify-center px-5">Log in</Link>
        </> : <p>{result.message}</p>}
      </section>}
    </form>
  );
}
