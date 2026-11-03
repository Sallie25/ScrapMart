import Link from "next/link";
import { AuthShell, AuthBack } from "@/components/auth/auth-shell";
import { SignupForm } from "@/components/forms/signup-form";

export default async function SignupPage({
  searchParams,
}: {
  searchParams: Promise<{ role?: string }>;
}) {
  const { role: requestedRole } = await searchParams;
  const role = requestedRole === "vendor" ? "vendor" : "buyer";
  const vendor = role === "vendor";
  return (
    <AuthShell>
      <div
        className={`auth-panel mx-auto grid max-w-5xl overflow-hidden rounded-3xl lg:grid-cols-[.72fr_1fr] ${vendor ? "auth-vendor-signup" : ""}`}
      >
        <aside className="auth-dark-panel hidden p-9 text-white lg:block">
          <span className="auth-step-badge inline-flex rounded-full px-3 py-1 text-xs font-bold">
            {vendor ? "Step 1 of 3" : "Buyer registration"}
          </span>
          <h2 className="auth-display mt-7 text-4xl font-extrabold">
            {vendor
              ? "Set up your shop and reach buyers."
              : "Start finding scrap near you."}
          </h2>
          <p className="mt-4 text-slate-300">
            {vendor
              ? "Vendor identity review is planned to help keep ScrapMart safe for everyone."
              : "Discover local materials and always pay on delivery."}
          </p>
          <div className="mt-10 rounded-2xl bg-white/10 p-5">
            <p className="text-sm font-bold text-[#74d99b]">Safety first</p>
            <p className="mt-2 text-sm leading-relaxed text-slate-300">
              {vendor
                ? "Identification upload and review are not connected. Do not submit identity documents in this demo."
                : "Registration uses ScrapMart authentication when the service is available."}
            </p>
          </div>
        </aside>
        <section className="min-w-0 p-6 md:p-9">
          <AuthBack href={`/onboarding?intent=${vendor ? "sell" : "buy"}`} />
          <h1 className="auth-display text-3xl font-extrabold">
            Create {role} account
          </h1>
          <p className="auth-muted mt-2 text-sm">
            {vendor ? "Fill in the required details to preview registration." : "Fill in the required details to create a Buyer account."}
          </p>
          <SignupForm key={role} role={role} />
          <p className="auth-muted mt-5 text-center text-sm">
            Already have an account?{" "}
            <Link className="auth-green font-bold" href={`/login?role=${role}`}>
              Log in
            </Link>
          </p>
          <p className="auth-muted mt-3 text-center text-sm">
            {vendor ? "Want to buy instead?" : "Want to sell instead?"}{" "}
            <Link
              className="auth-green font-bold"
              href={`/signup?role=${vendor ? "buyer" : "vendor"}`}
            >
              Switch registration type
            </Link>
          </p>
        </section>
      </div>
    </AuthShell>
  );
}
