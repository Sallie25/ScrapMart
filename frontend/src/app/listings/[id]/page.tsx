import Link from "next/link";
import { BuyerShell } from "@/components/buyer/buyer-shell";
import { ListingDetails } from "@/components/buyer/listing-details";
import { LiveListingDetails } from "@/components/buyer/live-listing-details";
import { resourceId } from "@/lib/marketplace/catalogue";
import { safeCatalogueReturn } from "@/lib/marketplace/query";
import { MarketplaceError, marketplaceClient } from "@/lib/server/marketplace/client";

export default async function ListingDetailsPage({ params, searchParams }: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ returnTo?: string | string[] }>;
}) {
  const { id } = await params;
  if (!resourceId.safeParse(id).success) return <BuyerShell variant="public"><ListingDetails key={id} id={id} /></BuyerShell>;
  const { returnTo } = await searchParams;
  const back = safeCatalogueReturn(returnTo);
  let listing;
  let failure: unknown;
  try { listing = await marketplaceClient().listing(id); }
  catch (error) { failure = error; }
  if (listing) return <BuyerShell variant="public" publicNotice="Live listing · Availability and vendor verification come from the marketplace API."><LiveListingDetails listing={listing} returnTo={back} /></BuyerShell>;
  const missing = failure instanceof MarketplaceError && failure.kind === "not_found";
  return <BuyerShell variant="public" publicNotice="Live marketplace listing"><section role="alert" className="buyer-card p-8 text-center"><h1 className="buyer-title">{missing ? "Listing not found" : "Listing unavailable"}</h1><p className="buyer-muted mt-3">{missing ? "This listing is no longer available." : "We could not load this listing. Please try again."}</p>{!missing && <Link href={`/listings/${id}?${new URLSearchParams({ returnTo: back })}`} className="buyer-button mt-6 mr-2">Retry</Link>}<Link href={back} className="buyer-button buyer-ghost mt-6">Back to results</Link></section></BuyerShell>;
}
