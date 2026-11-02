"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { AuthField } from "@/components/auth/auth-field";
import { loginSchema, type LoginFormValues } from "@/lib/validations/auth";

export function LoginForm({ role = "buyer" }: { role?: "buyer" | "vendor" }) {
  const [showPassword, setShowPassword] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });
  return (
    <form
      onSubmit={handleSubmit(() => setSubmitted(true))}
      onChange={() => setSubmitted(false)}
      className="mt-6 grid gap-4"
      noValidate
    >
      <p className="auth-muted text-xs leading-relaxed">
        Demo only · Use an email address to preview sign-in. No credentials are
        sent or stored.
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
      <Button type="submit" block className="auth-button mt-2">
        Log in
      </Button>
      {submitted && (
        <p role="status" className="auth-status">
          Validation passed. This prototype does not authenticate users or start
          a session. No sign-in request was sent.
        </p>
      )}
    </form>
  );
}
