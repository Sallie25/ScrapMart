"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { buyerLoginDestination, createBuyerAuthClient } from "@/lib/buyer-auth";
import { createVendorAuthClient } from "@/lib/vendor-auth";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { AuthField } from "@/components/auth/auth-field";
import { loginSchema, type LoginFormValues } from "@/lib/validations/auth";

export function LoginForm({ role = "buyer", returnTo }: { role?: "buyer" | "vendor"; returnTo?: string | null }) {
  const [showPassword, setShowPassword] = useState(false);
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState("");
  const inFlight = useRef(false);
  const client = useRef(createBuyerAuthClient());
  const vendorClient = useRef(createVendorAuthClient());
  const router = useRouter();
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });
  const submitLogin = async (values: LoginFormValues) => {
    if (inFlight.current) return;
    inFlight.current = true; setPending(true); setResult("");
    try {
      const outcome = await (role === "buyer" ? client.current.login(values) : vendorClient.current.login(values));
      const destination = role === "buyer" ? (buyerLoginDestination(outcome) && returnTo || buyerLoginDestination(outcome)) :
        outcome.status === "authenticated" ? "/vendor/dashboard" : null;
      if (destination) { router.replace(destination); }
      else {
        for (const field of outcome.fields ?? []) if (field === "email" || field === "password") setError(field, { message: `Check ${field}.` });
        setResult(outcome.message);
      }
    } finally { inFlight.current = false; setPending(false); }
  };
  return (
    <form
      onSubmit={event => { void handleSubmit(submitLogin)(event); }}
      onChange={() => setResult("")}
      className="mt-6 grid gap-4"
      noValidate
    >
      <p className="auth-muted text-xs leading-relaxed">
        Sign in through ScrapMart authentication. Your account permissions are checked by the backend.
      </p>
      <AuthField
        id="login-email"
        label="Email address"
        type="email"
        autoComplete="username"
        placeholder="name@example.com"
        required
        error={errors.email?.message}
        {...register("email")}
      />
      <div>
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <AuthField
              id="login-password"
              label="Password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              placeholder="Your password"
              required
              error={errors.password?.message}
              {...register("password")}
            />
          </div>
          <button
            type="button"
            className="auth-password-toggle mt-6"
            onClick={() => setShowPassword(!showPassword)}
            aria-label={showPassword ? "Hide password" : "Show password"}
            aria-pressed={showPassword}
          >
            {showPassword ? "Hide" : "Show"}
          </button>
        </div>
      </div>
      <Link
        href={`/forgot-password?role=${role}`}
        className="auth-green w-fit text-sm font-bold"
      >
        Forgot password?
      </Link>
      <Button type="submit" block className="auth-button mt-2" disabled={pending} loading={pending}>
        {pending ? "Signing in…" : "Log in"}
      </Button>
      {result && <p role="alert" className="auth-status text-red-700">{result}</p>}
    </form>
  );
}
