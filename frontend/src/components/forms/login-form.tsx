
"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function LoginForm() {
  const [showPassword, setShowPassword] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    // Prototype only: authentication is not connected yet.
    setSubmitted(true);
  }

  return (
    <Card>
      <form onSubmit={handleSubmit} className="space-y-5">
        <div>
          <Label htmlFor="loginIdentifier" required>
            Email address or phone number
          </Label>
          <Input
            id="loginIdentifier"
            name="loginIdentifier"
            type="text"
            placeholder="Enter your email or phone number"
            autoComplete="username"
            required
          />
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
              name="password"
              type={showPassword ? "text" : "password"}
              placeholder="Enter your password"
              autoComplete="current-password"
              required
              className="min-w-0"
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
        </div>

        <Button type="submit" block>
          Log in
        </Button>

        {submitted && (
          <p
            role="status"
            className="rounded-lg border border-border bg-background p-3 text-sm text-text"
          >
            Form submitted for prototype testing. You are not logged in
            because authentication is not connected yet.
          </p>
        )}
      </form>
    </Card>
  );
}