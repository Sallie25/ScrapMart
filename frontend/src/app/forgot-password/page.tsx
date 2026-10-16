
"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { SiteHeader } from "@/components/layout/site-header";
import { Container } from "@/components/ui/container";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitted(true);
  }

  return (
    <>
      <SiteHeader />
      <main className="min-h-screen bg-background px-4 py-12">
        <Container>
          <div className="mx-auto max-w-md rounded-2xl border border-border bg-white p-6 sm:p-8">
            <h1 className="text-2xl font-bold text-text">
              Forgot your password?
            </h1>
            <p className="mt-3 leading-6 text-muted">
              Enter your email address to try the password recovery demo.
            </p>

            {submitted ? (
              <div className="mt-6 rounded-lg border border-border p-4">
                <p className="font-semibold text-text">
                  Demo interaction completed
                </p>
                <p className="mt-2 text-sm leading-6 text-muted">
                  No recovery email was sent. Password recovery will be
                  available after backend authentication is integrated.
                </p>
                <button
                  type="button"
                  onClick={() => setSubmitted(false)}
                  className="mt-4 font-semibold text-primary hover:underline"
                >
                  Try again
                </button>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="mt-6 space-y-4">
                <div>
                  <label
                    htmlFor="recovery-email"
                    className="mb-2 block text-sm font-medium text-text"
                  >
                    Email address
                  </label>
                  <input
                    id="recovery-email"
                    type="email"
                    required
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="you@example.com"
                    className="w-full rounded-lg border border-border bg-white px-4 py-3 text-text outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                  />
                </div>

                <button
                  type="submit"
                  className="w-full rounded-lg bg-primary px-4 py-3 font-semibold text-white hover:opacity-90"
                >
                  Continue
                </button>
              </form>
            )}

            <Link
              href="/login"
              className="mt-6 inline-block text-sm font-semibold text-primary hover:underline"
            >
              ← Back to login
            </Link>
          </div>
        </Container>
      </main>
    </>
  );
}
