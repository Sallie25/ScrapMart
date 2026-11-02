import { BuyerShell } from "@/components/buyer/buyer-shell";
import { BuyerDashboard } from "@/components/buyer/buyer-dashboard";
export default async function BuyerDashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ view?: string }>;
}) {
  const { view } = await searchParams;
  return (
    <BuyerShell view={view}>
      <BuyerDashboard view={view} />
    </BuyerShell>
  );
}
