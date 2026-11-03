"use client";

import { useRef, useState } from "react";
import { createBuyerAuthClient } from "@/lib/buyer-auth";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { AuthField } from "@/components/auth/auth-field";
import { AuthIcon } from "@/components/auth/auth-icon";
import {
  buyerSignupSchema,
  vendorSignupSchema,
  type SignupFormValues,
} from "@/lib/validations/auth";

const buyerFormSchema = buyerSignupSchema.extend({ previewConsent: z.boolean().refine(Boolean, "Confirm the registration acknowledgement") });

export function SignupForm({ role }: { role: "buyer" | "vendor" }) {
  const vendor = role === "vendor";
  const [submitted, setSubmitted] = useState(false);
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<{ message: string; accepted: boolean } | null>(null);
  const inFlight = useRef(false);
  const client = useRef(createBuyerAuthClient());
  const [showPassword, setShowPassword] = useState(false);
  const form = useForm<SignupFormValues>({
    resolver: zodResolver(vendor ? vendorSignupSchema : buyerFormSchema),
    defaultValues: {
      fullName: "",
      phone: "",
      email: "",
      password: "",
      previewConsent: false,
      ...(vendor
        ? { businessName: "", businessLocation: "", businessAddress: "" }
        : {}),
    },
  });
  const { register, handleSubmit, getFieldState, formState } = form;
  const submitBuyer = async (values: SignupFormValues) => {
    if (inFlight.current) return;
    inFlight.current = true; setPending(true); setResult(null);
    try {
      const outcome = await client.current.signup(values);
      if (outcome.status === "accepted") form.resetField("password");
      else for (const field of outcome.fields ?? []) {
        const name = { full_name: "fullName", phone_number: "phone", email: "email", password: "password" }[field] as "fullName" | "phone" | "email" | "password" | undefined;
        if (name) form.setError(name, { message: `Check ${name === "fullName" ? "full name" : name === "phone" ? "phone number" : name}.` });
      }
      setResult({ message: outcome.message, accepted: outcome.status === "accepted" });
    } finally { inFlight.current = false; setPending(false); }
  };
  const fieldError = (name: Parameters<typeof getFieldState>[0]) =>
    getFieldState(name, formState).error?.message;
  return (
    <form
      onChange={() => { setSubmitted(false); setResult(null); }}
      onSubmit={event => { void handleSubmit(vendor ? async () => { setSubmitted(true); form.resetField("password"); } : submitBuyer)(event); }}
      className="mt-7"
      noValidate
    >
      <p
        className={`auth-muted mb-5 text-xs leading-relaxed ${vendor ? "sr-only" : ""}`}
      >
        {vendor ? "Demo only · Details are validated in this form and are not sent or stored. No account or OTP is created." : "Submit your details through ScrapMart authentication. Registration may be unavailable until the service is activated."}
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
            <AuthField
              id="signup-business-location"
              label="Shop location"
              placeholder="Ikeja, Lagos"
              autoComplete="address-level2"
              required
              error={fieldError("businessLocation")}
              {...register("businessLocation")}
            />
            <div className="md:col-span-2">
              <AuthField
                id="signup-business-address"
                label="Shop address"
                placeholder="Computer Village area, Ikeja"
                autoComplete="street-address"
                required
                error={fieldError("businessAddress")}
                {...register("businessAddress")}
              />
            </div>
            <div>
              <label htmlFor="identification-type" className="mb-2 block">
                Identification type
              </label>
              <select
                id="identification-type"
                disabled
                aria-describedby="identity-demo"
              >
                <option>National ID</option>
                <option>Driver&apos;s Licence</option>
                <option>International Passport</option>
                <option>Voter&apos;s Card</option>
              </select>
            </div>
            <div>
              <label htmlFor="identification-document" className="mb-2 block">
                Identification upload
              </label>
              <label className="auth-upload flex min-h-12 items-center gap-3 rounded-xl px-4 opacity-65">
                <AuthIcon name="upload" />
                <span>Upload unavailable</span>
                <input
                  id="identification-document"
                  type="file"
                  className="sr-only"
                  disabled
                  aria-describedby="identity-demo"
                />
              </label>
            </div>
          </>
        )}
      </div>
      <p
        className={`auth-helper mt-4 text-xs leading-relaxed ${vendor ? "sr-only" : ""}`}
      >
        Passwords are checked against the backend signup rules without trimming
        or changing them. {vendor ? "This is a demo; use a sample password, not a real one." : "Your password is sent only to the same-origin authentication route."}
      </p>
      {vendor && (
        <p
          id="identity-demo"
          className="auth-helper mt-3 text-xs leading-relaxed"
        >
          ID upload and review are unavailable. Shop details are a separate
          onboarding step; nothing is sent or stored here.
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
          {vendor ? (
            <>
              I understand this is a demo.{" "}
              <strong>Terms and Privacy Policy</strong> are not connected; no
              account will be created.
            </>
          ) : (
            "I understand registration is only confirmed by the authentication service."
          )}
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
        {vendor ? "Create account (demo)" : pending ? "Submitting…" : "Create buyer account"}
      </Button>
      {result && <section role={result.accepted ? "status" : "alert"} className="auth-status mt-5"><p>{result.message}</p></section>}
      {submitted && (
        <section role="status" className="auth-status mt-5">
          <h2 className="auth-display font-extrabold">
            Registration preview completed
          </h2>
          <p>
            No account was created and no data was sent.{" "}
            {vendor
              ? "Identity review remains required; you are not verified or approved."
              : "No verification code was sent."}
          </p>
          <button
            type="button"
            className="auth-green mt-3 text-sm font-bold underline"
            onClick={() => setSubmitted(false)}
          >
            Continue editing
          </button>
        </section>
      )}
    </form>
  );
}
