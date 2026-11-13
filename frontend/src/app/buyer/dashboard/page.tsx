import Link from "next/link";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { BuyerShell } from "@/components/buyer/buyer-shell";
import { BuyerDashboard } from "@/components/buyer/buyer-dashboard";
import { BuyerSessionReady, BuyerSessionRefresh } from "@/components/buyer/buyer-session-refresh";
import { buyerSessionDecision } from "@/lib/server/auth/buyer-session";
import { marketplaceClient } from "@/lib/server/marketplace/client";
import { loadMarketplace } from "@/lib/server/marketplace/page-data";

export default async function BuyerDashboardPage({ searchParams }: {
  searchParams: Promise<{ view?: string }>;
}) {
  const decision = await buyerSessionDecision((await headers()).get('cookie'));
  if (decision === 'login') redirect('/login?role=buyer');
  if (decision === 'refresh') return <BuyerShell><BuyerSessionRefresh /></BuyerShell>;
  if (decision === 'unavailable') return <BuyerShell><section role="alert" className="buyer-card p-8 text-center"><h1 className="buyer-title">Buyer account unavailable</h1><p className="buyer-muted mt-3">We could not confirm your session. Please try again.</p><Link href="/buyer/dashboard" className="buyer-button mt-6">Retry</Link></section></BuyerShell>;
  const { view } = await searchParams;
  const marketplace = await loadMarketplace({}, marketplaceClient);
  return <BuyerShell view={view} authenticated><BuyerSessionReady /><BuyerDashboard view={view} marketplace={marketplace} /></BuyerShell>;
}
