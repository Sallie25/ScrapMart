
"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import type { SubmitHandler } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  loginSchema,
  type LoginFormValues,
} from "@/lib/validations/auth";

export function LoginForm() {
  const [showPassword, setShowPassword] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      loginIdentifier: "",
      password: "",
    },
  });

  const onSubmit: SubmitHandler<LoginFormValues> = () => {
    // Prototype only: no credentials are sent to a server.
    setSubmitted(true);
  };

  return (
    <Card>
      <form
        onSubmit={handleSubmit(onSubmit)}
        className="space-y-5"
        noValidate
      >
        <div>
          <Label htmlFor="loginIdentifier" required>
            Email address or phone number
          </Label>

          <Input
            id="loginIdentifier"
            type="text"
            placeholder="Enter your email or phone number"
            autoComplete="username"
            error={Boolean(errors.loginIdentifier)}
            aria-invalid={Boolean(errors.loginIdentifier)}
            aria-describedby={
              errors.loginIdentifier
                ? "loginIdentifier-error"
                : undefined
            }
            {...register("loginIdentifier")}
          />

          {errors.loginIdentifier && (
            <p
              id="loginIdentifier-error"
              role="alert"
              className="mt-1.5 text-sm text-error"
            >
              {errors.loginIdentifier.message}
            </p>
          )}
        </div>

        <div>
          <div className="mb-1.5 flex items-center justify-between gap-3">
            <Label htmlFor="password" required>
              Password
            </Label>

            <Link
              href="/forgot-password"
              className="text-sm font-medium text-primary hover:underline"
            >
              Forgot password?
            </Link>
          </div>

          <div className="flex items-center gap-2">
            <Input
              id="password"
              type={showPassword ? "text" : "password"}
              placeholder="Enter your password"
              autoComplete="current-password"
              error={Boolean(errors.password)}
              aria-invalid={Boolean(errors.password)}
              aria-describedby={
                errors.password ? "password-error" : undefined
              }
              className="min-w-0"
              {...register("password")}
            />

            <Button
              type="button"
              variant="secondary"
              onClick={() => setShowPassword((current) => !current)}
              aria-label={showPassword ? "Hide password" : "Show password"}
            >
              {showPassword ? "Hide" : "Show"}
            </Button>
          </div>

          {errors.password && (
            <p
              id="password-error"
              role="alert"
              className="mt-1.5 text-sm text-error"
            >
              {errors.password.message}
            </p>
          )}
        </div>

        <Button type="submit" block>
          Log in
        </Button>

        {submitted && (
          <p
            role="status"
            className="rounded-lg border border-border bg-background p-3 text-sm text-text"
          >
            Validation passed. This prototype does not authenticate
            users yet.
          </p>
        )}
      </form>
    </Card>
  );
}