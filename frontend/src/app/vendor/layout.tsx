import type { ReactNode } from "react";
import Link from "next/link";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { BuyerSessionReady, BuyerSessionRefresh } from "@/components/buyer/buyer-session-refresh";
import { VendorShell } from "@/components/vendor/vendor-shell";
import { vendorSessionDecision } from "@/lib/server/auth/vendor-session";

export default async function VendorLayout({ children }: { children: ReactNode }) {
  const decision = await vendorSessionDecision((await headers()).get("cookie"));
  if (decision.kind === "login") redirect("/login?role=vendor");
  if (decision.kind === "refresh") return <VendorShell><BuyerSessionRefresh role="vendor" /></VendorShell>;
  if (decision.kind === "forbidden") return <VendorShell><section role="alert" className="vendor-card p-8"><h1 className="vendor-title">Vendor account required</h1><p className="vendor-muted mt-3">This account has no Vendor profile.</p><Link href="/signup?role=vendor" className="vendor-button mt-5">Create a Vendor account</Link></section></VendorShell>;
  if (decision.kind === "unavailable") return <VendorShell><section role="alert" className="vendor-card p-8"><h1 className="vendor-title">Vendor account unavailable</h1><p className="vendor-muted mt-3">We could not confirm your account or verification status.</p></section></VendorShell>;
  return <VendorShell><BuyerSessionReady /><div role="status" className="vendor-card mb-4 px-4 py-3 text-sm">Verification: <strong>{decision.verificationStatus}</strong>{decision.verificationStatus !== "approved" && " · Selling requires backend approval."}</div>{children}</VendorShell>;
}
