import { BuyerShell } from "@/components/buyer/buyer-shell";
import { MarketplaceDiscovery } from "@/components/buyer/marketplace-discovery";
import type { SearchParameters } from "@/lib/marketplace/query";
import { marketplaceClient } from "@/lib/server/marketplace/client";
import { loadMarketplace } from "@/lib/server/marketplace/page-data";

export default async function MarketplacePage({ searchParams }: { searchParams: Promise<SearchParameters> }) {
  const raw = await searchParams;
  const view = await loadMarketplace(raw, marketplaceClient);
  return <BuyerShell variant="public" publicNotice="Live catalogue · Listings and vendor verification come from the marketplace API."><MarketplaceDiscovery key={JSON.stringify(raw)} {...view} /></BuyerShell>;
}
