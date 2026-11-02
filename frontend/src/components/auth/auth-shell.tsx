import type { ReactNode } from "react";
import Link from "next/link";
import localFont from "next/font/local";
import { AuthIcon } from "./auth-icon";
import "./auth.css";

const dmSans = localFont({
  src: "../../app/fonts/dm-sans.woff2",
  weight: "400 800",
  variable: "--font-auth-dm",
  display: "swap",
});
const manrope = localFont({
  src: "../../app/fonts/manrope.woff2",
  weight: "600 800",
  variable: "--font-auth-manrope",
  display: "swap",
});

export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <main
      className={`${dmSans.variable} ${manrope.variable} sm-auth min-h-screen p-4 md:p-8`}
    >
      <div className="mx-auto max-w-6xl">
        <header className="mb-8 flex items-center justify-between gap-3">
          <Link
            href="/"
            aria-label="ScrapMart home"
            className="flex items-center gap-2 text-left"
          >
            <span className="auth-logo-icon grid size-9 place-items-center rounded-xl text-white">
              <AuthIcon name="store" />
            </span>
            <span className="auth-display text-xl font-extrabold tracking-tight">
              Scrap<span className="auth-green">Mart</span>
            </span>
          </Link>
          <span className="auth-badge shrink-0 rounded-full px-3 py-1.5 text-xs font-extrabold">
            PAY ON DELIVERY
          </span>
        </header>
        {children}
      </div>
    </main>
  );
}
export function AuthBack({
  href = "/onboarding",
  children = "Back",
}: {
  href?: string;
  children?: ReactNode;
}) {
  return (
    <Link
      href={href}
      className="auth-back mb-5 inline-flex min-h-11 items-center gap-2 text-sm font-bold"
    >
      <AuthIcon name="arrow" />
      {children}
    </Link>
  );
}
