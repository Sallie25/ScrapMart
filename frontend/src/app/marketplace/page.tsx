import { BuyerShell } from "@/components/buyer/buyer-shell";
import { MarketplaceDiscovery } from "@/components/buyer/marketplace-discovery";
import { buyerListings } from "@/lib/data/buyer-fixtures";
export default async function MarketplacePage({
  searchParams,
}: {
  searchParams: Promise<{ category?: string; q?: string }>;
}) {
  const { category, q } = await searchParams;
  const initialCategory =
    buyerListings.find(
      (l) => l.category.toLowerCase() === (category ?? "").trim().toLowerCase(),
    )?.category ?? "All";
  return (
    <BuyerShell>
      <MarketplaceDiscovery
        key={`${category ?? ""}:${q ?? ""}`}
        initialCategory={initialCategory}
        initialQuery={q ?? ""}
      />
    </BuyerShell>
  );
}
