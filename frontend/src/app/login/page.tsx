import Link from "next/link";
import { safeListingReturn } from "@/lib/marketplace/buyer-actions";
import { AuthShell } from "@/components/auth/auth-shell";
import { LoginForm } from "@/components/forms/login-form";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ role?: string; returnTo?: string }>;
}) {
  const { role: requestedRole, returnTo } = await searchParams;
  const destination = safeListingReturn(returnTo);
  const role = requestedRole === "vendor" ? "vendor" : "buyer";
  return (
    <AuthShell>
      <div className="auth-panel mx-auto grid max-w-4xl overflow-hidden rounded-3xl md:grid-cols-[.8fr_1fr]">
        <aside className="auth-dark-panel p-8 text-white">
          <span className="auth-step-badge inline-flex rounded-full px-3 py-1 text-xs font-bold">
            Welcome back
          </span>
          <h2 className="auth-display mt-6 text-3xl font-extrabold">
            Your marketplace is ready.
          </h2>
          <p className="mt-3 text-sm leading-relaxed text-slate-300">
            {role === "buyer" ? "Sign in through ScrapMart authentication to access your Buyer account when the service is available." : "Sign in to access your saved orders, listings and messages when authentication is connected."}
          </p>
          <div className="mt-8 rounded-2xl bg-white/10 p-4">
            <p className="text-xs font-bold uppercase tracking-wider text-[#74d99b]">
              Signing in as
            </p>
            <p className="auth-display mt-1 text-xl font-extrabold">
              {role === "buyer" ? "Buyer" : "Vendor"}
            </p>
            <Link
              href={`/login?role=${role === "buyer" ? "vendor" : "buyer"}`}
              className="mt-3 inline-block text-sm font-bold text-white underline underline-offset-4"
            >
              Switch to {role === "buyer" ? "Vendor" : "Buyer"}
            </Link>
          </div>
        </aside>
        <section className="min-w-0 p-7 md:p-9">
          <p className="auth-eyebrow">{role} sign in</p>
          <h1 className="auth-title">Welcome back</h1>
          {destination && (
            <p role="note" className="auth-status mt-4">
              {role === "buyer" ? "Sign-in is required for this buyer action. Contact and ordering are not yet connected." : "Sign-in required for this buyer action. This login is still a demonstration and cannot authenticate or submit messages/orders."}{" "}
              <Link href={destination} className="underline">
                Return to item
              </Link>
            </p>
          )}
          <LoginForm key={role} role={role} />
          <p className="auth-muted mt-5 text-center text-sm">
            New to ScrapMart?{" "}
            <Link
              href={`/onboarding?intent=${role === "vendor" ? "sell" : "buy"}`}
              className="auth-green font-bold"
            >
              Create an account
            </Link>
          </p>
        </section>
      </div>
    </AuthShell>
  );
}
