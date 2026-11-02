import type { ReactNode } from "react";
import localFont from "next/font/local";
import { BuyerNavigation } from "./buyer-navigation";
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
}: {
  children: ReactNode;
  view?: string;
}) {
  return (
    <div className={`${dmSans.variable} ${manrope.variable} sm-buyer`}>
      <BuyerNavigation view={view} />
      <div className="lg:pl-64">
        <main className="mx-auto min-h-[calc(100vh-5rem)] max-w-screen-2xl px-4 pb-10 pt-5 lg:px-7 lg:pt-6">
          <div className="mb-5 rounded-xl border border-[#dfe6e1] bg-white px-4 py-3 text-xs leading-relaxed text-[#627067]">
            Presentation preview · Sample listings and profile; no authenticated
            session, live orders, messages or verified vendor claims.
          </div>
          {children}
        </main>
      </div>
    </div>
  );
}
