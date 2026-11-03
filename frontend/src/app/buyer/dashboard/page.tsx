import Link from "next/link";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { BuyerShell } from "@/components/buyer/buyer-shell";
import { BuyerDashboard } from "@/components/buyer/buyer-dashboard";
import { buyerSessionDecision } from "@/lib/server/auth/buyer-session";

export default async function BuyerDashboardPage({ searchParams }: {
  searchParams: Promise<{ view?: string }>;
}) {
  const decision = await buyerSessionDecision((await headers()).get('cookie'));
  if (decision === 'login') redirect('/login?role=buyer');
  if (decision === 'unavailable') return <BuyerShell><section role="alert" className="buyer-card p-8 text-center"><h1 className="buyer-title">Buyer account unavailable</h1><p className="buyer-muted mt-3">We could not confirm your session. Please try again.</p><Link href="/buyer/dashboard" className="buyer-button mt-6">Retry</Link></section></BuyerShell>;
  const { view } = await searchParams;
  return <BuyerShell view={view}><BuyerDashboard view={view} /></BuyerShell>;
}
