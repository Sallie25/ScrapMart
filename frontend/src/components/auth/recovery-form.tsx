"use client";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { AuthField } from "./auth-field";
import { Button } from "@/components/ui/button";
const recoverySchema = z.object({
  email: z.string().trim().email("Enter a valid email address"),
});
export function RecoveryForm() {
  const [submitted, setSubmitted] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<z.infer<typeof recoverySchema>>({
    resolver: zodResolver(recoverySchema),
    defaultValues: { email: "" },
  });
  return (
    <form
      className="mt-6 grid gap-4"
      onChange={() => setSubmitted(false)}
      onSubmit={handleSubmit(() => setSubmitted(true))}
      noValidate
    >
      <p className="auth-muted text-xs leading-relaxed">
        Demo only · No recovery email or OTP will be sent.
      </p>
      <AuthField
        id="recovery-email"
        label="Email address"
        type="email"
        autoComplete="email"
        placeholder="name@example.com"
        required
        error={errors.email?.message}
        {...register("email")}
      />
      <Button type="submit" block className="auth-button">
        Preview recovery
      </Button>
      {submitted && (
        <div role="status" className="auth-status">
          <p className="font-bold">Demo interaction completed</p>
          <p>
            No recovery request was sent. Password recovery is not connected to
            the backend.
          </p>
        </div>
      )}
    </form>
  );
}
