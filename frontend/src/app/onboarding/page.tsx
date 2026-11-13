import Link from "next/link";
import { AuthShell } from "@/components/auth/auth-shell";
import { AuthIcon } from "@/components/auth/auth-icon";

export default async function OnboardingPage({
  searchParams,
}: {
  searchParams: Promise<{ intent?: string }>;
}) {
  const { intent } = await searchParams;
  return (
    <AuthShell>
      <div className="mx-auto max-w-4xl text-center">
        <p className="auth-eyebrow">Let’s get you started</p>
        <h1 className="auth-display mt-3 text-4xl font-extrabold tracking-tight">
          What do you want to do?
        </h1>
        <p className="auth-muted mt-3">
          Choose an option. You can explore the other side later.
        </p>
        <div className="mt-10 grid gap-5 md:grid-cols-2">
          <article
            className={`auth-panel rounded-3xl border-2 p-7 text-left transition hover:border-[#08783e] ${intent === "buy" ? "border-[#08783e]" : "border-transparent"}`}
          >
            <span className="auth-badge grid size-14 place-items-center rounded-2xl">
              <AuthIcon name="bag" className="size-7" />
            </span>
            <h2 className="auth-display mt-6 text-2xl font-extrabold">
              Buy scrap
            </h2>
            <p className="auth-muted mt-2 min-h-12">
              Find clothes, scrap, used items and materials near you.
            </p>
            {intent === "buy" && (
              <p className="auth-green mt-3 text-sm font-bold">
                Your selection
              </p>
            )}
            <Link
              className="auth-link-button mt-6 w-full"
              href="/signup?role=buyer"
            >
              Create buyer account
            </Link>
            <Link
              href="/login?role=buyer"
              className="auth-green mt-3 block w-full py-2 text-center text-sm font-bold"
            >
              I already have a buyer account
            </Link>
          </article>
          <article
            className={`auth-ink-panel rounded-3xl border-2 p-7 text-left text-white shadow-sm transition hover:border-[#74d99b] ${intent === "sell" ? "border-[#74d99b]" : "border-transparent"}`}
          >
            <span className="grid size-14 place-items-center rounded-2xl bg-white/10 text-[#74d99b]">
              <AuthIcon name="store" className="size-7" />
            </span>
            <h2 className="auth-display mt-6 text-2xl font-extrabold">
              Sell scrap
            </h2>
            <p className="mt-2 min-h-12 text-slate-300">
              List your scrap and reach local buyers.
            </p>
            {intent === "sell" && (
              <p className="mt-3 text-sm font-bold text-[#74d99b]">
                Your selection
              </p>
            )}
            <Link
              className="auth-link-button mt-6 w-full"
              href="/signup?role=vendor"
            >
              Create vendor account
            </Link>
            <Link
              href="/login?role=vendor"
              className="mt-3 block w-full py-2 text-center text-sm font-bold text-[#74d99b]"
            >
              I already have a vendor account
            </Link>
          </article>
        </div>
        <p className="auth-muted mt-6 text-xs">
          Account requests are handled by ScrapMart authentication when the service is available.
        </p>
      </div>
    </AuthShell>
  );
}
