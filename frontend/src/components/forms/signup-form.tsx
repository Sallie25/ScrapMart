"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@/components/ui/button";
import { AuthField } from "@/components/auth/auth-field";
import { AuthIcon } from "@/components/auth/auth-icon";
import {
  buyerSignupSchema,
  vendorSignupSchema,
  type SignupFormValues,
} from "@/lib/validations/auth";

export function SignupForm({ role }: { role: "buyer" | "vendor" }) {
  const vendor = role === "vendor";
  const [submitted, setSubmitted] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const form = useForm<SignupFormValues>({
    resolver: zodResolver(vendor ? vendorSignupSchema : buyerSignupSchema),
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
  const fieldError = (name: Parameters<typeof getFieldState>[0]) =>
    getFieldState(name, formState).error?.message;
  return (
    <form
      onChange={() => setSubmitted(false)}
      onSubmit={handleSubmit(() => {
        setSubmitted(true);
        form.resetField("password");
      })}
      className="mt-7"
      noValidate
    >
      <p className="auth-muted mb-5 text-xs leading-relaxed">
        Demo only · Details are validated in this form and are not sent or
        stored. No account or OTP is created.
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
                helper="15–128 characters. Unicode and spaces are allowed; not only whitespace. No null characters or invalid Unicode text."
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
      <p className="auth-helper mt-4 text-xs leading-relaxed">
        Passwords are checked against the backend signup rules without trimming
        or changing them. This is a demo; use a sample password, not a real one.
      </p>
      {vendor && (
        <div id="identity-demo" className="auth-status mt-5">
          <h2 className="auth-display font-extrabold">
            Vendor verification required
          </h2>
          <p>
            Government-ID upload, storage and administrator review are not
            connected. Submitting this demo does not verify or approve a vendor.
            Publishing will require actual approval.
          </p>
        </div>
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
        <span>I understand this is a demo and no account will be created.</span>
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
      <p id="preview-terms" className="auth-helper mt-2 text-xs">
        Terms and Privacy Policy pages are not available yet.
      </p>
      <Button type="submit" block className="auth-button mt-6">
        Preview {role} registration
      </Button>
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
