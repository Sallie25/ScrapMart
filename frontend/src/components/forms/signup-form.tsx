
"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { FormField } from "@/components/ui/form-field";

type SignupFormProps = {
  role: "buyer" | "vendor";
};

export function SignupForm({ role }: SignupFormProps) {
  const [submitted, setSubmitted] = useState(false);
  const isVendor = role === "vendor";

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    // Prototype only: no account is created or data sent to a server.
    setSubmitted(true);
  }

  return (
    <Card>
      <form onSubmit={handleSubmit} className="space-y-5">
        <FormField
          id="fullName"
          label="Full name"
          placeholder="Enter your full name"
          required
        />

        <FormField
          id="email"
          label="Email address"
          type="email"
          placeholder="you@example.com"
          required
        />

        <FormField
          id="phone"
          label="Phone number"
          type="tel"
          placeholder="e.g. 08012345678"
          required
          helperText="Use a phone number you can access."
        />

        {isVendor && (
          <>
            <div className="border-t border-border pt-5">
              <h2 className="text-lg font-semibold text-text">
                Business details
              </h2>
              <p className="mt-1 text-sm text-muted">
                These details help buyers identify your shop.
              </p>
            </div>

            <FormField
              id="businessName"
              label="Shop or business name"
              placeholder="Enter your business name"
              required
            />

            <FormField
              id="businessAddress"
              label="Shop address or location"
              placeholder="Enter your shop location"
              required
              helperText="You can refine your location in a later step."
            />

            <div className="rounded-lg border border-border bg-background p-4">
              <h3 className="font-semibold text-text">
                Identity verification
              </h3>
              <p className="mt-2 text-sm leading-6 text-muted">
                Vendors must complete identity verification before
                using vendor features. Document submission and
                verification will be implemented in a later step.
              </p>
              <Badge variant="warning">Verification required</Badge>
            </div>
          </>
        )}

        <Button type="submit" block>
          {isVendor
            ? "Continue vendor registration"
            : "Continue buyer registration"}
        </Button>

        {submitted && (
          <p
            role="status"
            className="rounded-lg border border-border bg-background p-3 text-sm text-text"
          >
            Your form passed the browser&apos;s required-field checks.
            This is a prototype only; no account has been created
            and no information has been sent to a server.
          </p>
        )}
      </form>
    </Card>
  );
}