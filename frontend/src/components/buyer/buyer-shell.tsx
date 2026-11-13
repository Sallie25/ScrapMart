import type { ReactNode } from "react";
import localFont from "next/font/local";
import { BuyerNavigation } from "./buyer-navigation";
import { MarketplaceNavigation } from "./marketplace-navigation";
import "./buyer.css";
const dmSans = localFont({
  src: "../../app/fonts/dm-sans.woff2",
  weight: "400 800",
  variable: "--font-buyer-dm",
  display: "swap",
});
const manrope = localFont({
  src: "../../app/fonts/manrope.woff2",
  weight: "600 800",
  variable: "--font-buyer-manrope",
  display: "swap",
});
export function BuyerShell({
  children,
  view,
  variant = "workspace",
  publicNotice,
  authenticated = false,
}: {
  children: ReactNode;
  view?: string;
  variant?: "workspace" | "public";
  publicNotice?: string;
  authenticated?: boolean;
}) {
  return (
    <div className={`${dmSans.variable} ${manrope.variable} sm-buyer`}>
      {variant === "public" ? (
        <MarketplaceNavigation />
      ) : (
        <BuyerNavigation view={view} authenticated={authenticated} />
      )}
      <div className="lg:pl-64">
        <main className="mx-auto min-h-[calc(100vh-5rem)] max-w-screen-2xl px-4 pb-10 pt-5 lg:px-7 lg:pt-6">
          <div className="mb-5 rounded-xl border border-[#dfe6e1] bg-white px-4 py-3 text-xs leading-relaxed text-[#627067]">
            {variant === "public"
              ? publicNotice ?? "Presentation preview · Sample listings; live availability and vendor verification are not confirmed."
              : authenticated
                ? "Buyer session active · Marketplace listings come from ScrapMart. Orders and messages require separate account services."
                : "Presentation preview · Sample listings and profile; no authenticated session, live orders, messages or verified vendor claims."}
          </div>
          {children}
        </main>
      </div>
    </div>
  );
}
