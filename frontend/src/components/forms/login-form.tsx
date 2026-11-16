"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { buyerLoginDestination, createBuyerAuthClient } from "@/lib/buyer-auth";
import { createVendorAuthClient } from "@/lib/vendor-auth";
import { createLoginSessionClient, type ResolvedLoginSession } from "@/lib/login-session";
import { takeConfirmedLogout } from "@/lib/logout-feedback";
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
  const [notice, setNotice] = useState("");
  const [sessionState, setSessionState] = useState<ResolvedLoginSession | { status: "checking" }>({ status: "checking" });
  const existingRole = sessionState.status === "authenticated" ? sessionState.role : null;
  const inFlight = useRef(false);
  const client = useRef(createBuyerAuthClient());
  const vendorClient = useRef(createVendorAuthClient());
  const sessionClient = useRef(createLoginSessionClient());
  const router = useRouter();
  const {
    register,
    handleSubmit,
    setError,
    setValue,
    formState: { errors },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });
  useEffect(() => {
    let mounted = true;
    void sessionClient.current.resolve(role).then(session => {
      if (!mounted) return;
      setSessionState(session);
      if (session.status === "anonymous" && takeConfirmedLogout(role))
        setNotice("Signed out successfully.");
    });
    return () => { mounted = false; };
  }, [role]);
  const submitLogin = async (values: LoginFormValues) => {
    if (inFlight.current || sessionState.status !== "anonymous") return;
    inFlight.current = true; setPending(true); setResult(""); setNotice("");
    try {
      const outcome = await (role === "buyer" ? client.current.login(values) : vendorClient.current.login(values));
      const destination = role === "buyer" ? (buyerLoginDestination(outcome) && returnTo || buyerLoginDestination(outcome)) :
        outcome.status === "authenticated" ? "/vendor/dashboard" : null;
      if (destination) { router.replace(destination); }
      else {
        if (outcome.code === "logout_required") {
          setValue("password", "");
          const session = await sessionClient.current.resolve(role);
          setSessionState(session);
          if (session.status === "authenticated" || session.status === "unavailable") return;
          setResult("Your previous session is no longer active. Please try signing in again.");
          return;
        }
        for (const field of outcome.fields ?? []) if (field === "email" || field === "password") setError(field, { message: `Check ${field}.` });
        setResult(outcome.message);
      }
    } finally { inFlight.current = false; setPending(false); }
  };
  const switchAccount = async () => {
    if (inFlight.current || !existingRole) return;
    inFlight.current = true; setPending(true); setResult("");
    try {
      const outcome = await sessionClient.current.switchAccount(existingRole);
      if (outcome.status === "signed_out") {
        setValue("password", "");
        setSessionState({ status: "anonymous" });
        router.refresh();
      } else setResult(outcome.message);
    } finally { inFlight.current = false; setPending(false); }
  };
  const retrySessionCheck = async () => {
    if (inFlight.current) return;
    inFlight.current = true; setSessionState({ status: "checking" }); setResult("");
    try {
      const session = await sessionClient.current.resolve(role);
      setSessionState(session);
      if (session.status === "anonymous" && takeConfirmedLogout(role))
        setNotice("Signed out successfully.");
    }
    finally { inFlight.current = false; }
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
      <Button type="submit" block className="auth-button mt-2" disabled={pending || sessionState.status !== "anonymous"} loading={pending && !existingRole}>
        {pending && !existingRole ? "Signing in…" : "Log in"}
      </Button>
      {sessionState.status === "checking" && <p role="status" className="auth-status">Checking your session…</p>}
      {sessionState.status === "unavailable" && <div className="auth-status grid gap-3">
        <p role="alert">We could not check your current session. Please try again.</p>
        <Button type="button" block className="auth-button" onClick={() => void retrySessionCheck()}>Retry session check</Button>
      </div>}
      {existingRole && <div role="status" className="auth-status grid gap-3">
        <p>You&apos;re already signed in.</p>
        <Button type="button" block className="auth-button" disabled={pending}
          onClick={() => router.push(existingRole === "buyer" ? "/buyer/dashboard" : "/vendor/dashboard")}>
          Go to dashboard
        </Button>
        <Button type="button" block className="auth-button" disabled={pending} onClick={() => void switchAccount()}>
          {pending ? "Signing out…" : "Sign out and use another account"}
        </Button>
      </div>}
      {result && <p role="alert" className="auth-status text-red-700">{result}</p>}
      {notice && <p role="status" className="auth-status">{notice}</p>}
    </form>
  );
}
