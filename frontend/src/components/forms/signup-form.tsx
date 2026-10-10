
"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import type { SubmitHandler } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  buyerSignupSchema,
  vendorSignupSchema,
  type BuyerSignupValues,
  type VendorSignupValues,
} from "@/lib/validations/auth";

type SignupFormProps = {
  role: "buyer" | "vendor";
};

export function SignupForm({ role }: SignupFormProps) {
  const [submitted, setSubmitted] = useState(false);
  const isVendor = role === "vendor";

  const form = useForm<BuyerSignupValues | VendorSignupValues>({
    resolver: zodResolver(
      isVendor ? vendorSignupSchema : buyerSignupSchema,
    ),
    defaultValues: {
      fullName: "",
      email: "",
      phone: "",
      ...(isVendor
        ? { businessName: "", businessAddress: "" }
        : {}),
    },
  });

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = form;

  const onSubmit: SubmitHandler<
    BuyerSignupValues | VendorSignupValues
  > = () => {
    // Prototype only: no account or verification request is created.
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
          <Label htmlFor="fullName" required>Full name</Label>
          <Input
            id="fullName"
            autoComplete="name"
            placeholder="Enter your full name"
            error={Boolean(errors.fullName)}
            aria-invalid={Boolean(errors.fullName)}
            aria-describedby={errors.fullName ? "fullName-error" : undefined}
            {...register("fullName")}
          />
          {errors.fullName && (
            <p id="fullName-error" role="alert" className="mt-1.5 text-sm text-error">
              {errors.fullName.message}
            </p>
          )}
        </div>

        <div>
          <Label htmlFor="email" required>Email address</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            placeholder="you@example.com"
            error={Boolean(errors.email)}
            aria-invalid={Boolean(errors.email)}
            aria-describedby={errors.email ? "email-error" : undefined}
            {...register("email")}
          />
          {errors.email && (
            <p id="email-error" role="alert" className="mt-1.5 text-sm text-error">
              {errors.email.message}
            </p>
          )}
        </div>

        <div>
          <Label htmlFor="phone" required>Phone number</Label>
          <Input
            id="phone"
            type="tel"
            autoComplete="tel"
            placeholder="e.g. 08012345678"
            error={Boolean(errors.phone)}
            aria-invalid={Boolean(errors.phone)}
            aria-describedby={errors.phone ? "phone-error" : "phone-helper"}
            {...register("phone")}
          />
          {errors.phone ? (
            <p id="phone-error" role="alert" className="mt-1.5 text-sm text-error">
              {errors.phone.message}
            </p>
          ) : (
            <p id="phone-helper" className="mt-1.5 text-sm text-muted">
              Use a phone number you can access.
            </p>
          )}
        </div>

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

            <div>
              <Label htmlFor="businessName" required>
                Shop or business name
              </Label>
              <Input
                id="businessName"
                placeholder="Enter your business name"
                error={Boolean(
                  "businessName" in errors && errors.businessName,
                )}
                aria-invalid={Boolean(
                  "businessName" in errors && errors.businessName,
                )}
                {...register("businessName" as never)}
              />
              {"businessName" in errors && errors.businessName && (
                <p role="alert" className="mt-1.5 text-sm text-error">
                  {errors.businessName.message}
                </p>
              )}
            </div>

            <div>
              <Label htmlFor="businessAddress" required>
                Shop address or location
              </Label>
              <Input
                id="businessAddress"
                placeholder="Enter your shop location"
                error={Boolean(
                  "businessAddress" in errors && errors.businessAddress,
                )}
                aria-invalid={Boolean(
                  "businessAddress" in errors && errors.businessAddress,
                )}
                {...register("businessAddress" as never)}
              />
              {"businessAddress" in errors && errors.businessAddress && (
                <p role="alert" className="mt-1.5 text-sm text-error">
                  {errors.businessAddress.message}
                </p>
              )}
              <p className="mt-1.5 text-sm text-muted">
                You can refine your location in a later step.
              </p>
            </div>

            <div className="rounded-lg border border-border bg-background p-4">
              <h3 className="font-semibold text-text">
                Identity verification
              </h3>
              <p className="mt-2 text-sm leading-6 text-muted">
                Vendors must complete identity verification before using
                vendor features. Document submission and verification
                will be implemented separately.
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
          <p role="status" className="rounded-lg border border-border bg-background p-3 text-sm text-text">
            Validation passed. This is a prototype only; no account has
            been created and no information has been sent to a server.
          </p>
        )}
      </form>
    </Card>
  );
}