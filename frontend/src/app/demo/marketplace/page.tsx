import Link from "next/link";
import { BuyerShell } from "@/components/buyer/buyer-shell";
import { BuyerPhoto } from "@/components/buyer/buyer-listing-card";
import { ListingDetails } from "@/components/buyer/listing-details";
import { buyerListings } from "@/lib/data/buyer-fixtures";

export default async function SampleMarketplace({ searchParams }: {
  searchParams: Promise<{ item?: string | string[]; q?: string | string[] }>;
}) {
  const parameters = await searchParams;
  const item = typeof parameters.item === "string" ? parameters.item : undefined;
  const q = typeof parameters.q === "string" ? parameters.q.slice(0, 100) : "";
  const selected = buyerListings.find(listing => listing.id === item);
  const samples = buyerListings.filter(listing =>
    `${listing.title} ${listing.category} ${listing.location}`.toLowerCase().includes(q.toLowerCase()));
  return <BuyerShell variant="public" publicNotice="SAMPLE-DATA FALLBACK · Presentation fixtures only. No live inventory, messages, orders or payments.">
    <div className="buyer-card mb-6 p-5">
      <h1 className="buyer-title">Sample marketplace demonstration</h1>
      <p className="buyer-muted mt-3 text-sm">Vendor verification currently blocks the live listing journey. These existing design samples illustrate discovery, item details and contact controls. They are not available to buy.</p>
      <Link href="/marketplace" className="buyer-button buyer-ghost mt-4">Return to live marketplace</Link>
    </div>
    {selected ? <ListingDetails id={selected.id} returnTo="/demo/marketplace" /> : <>
      <form action="/demo/marketplace" className="buyer-card mb-6 flex flex-wrap gap-3 p-4">
        <label className="grid flex-1 gap-2 text-sm font-bold">Search sample scrap<input name="q" defaultValue={q} maxLength={100} className="rounded-md border border-border p-3" /></label>
        <button type="submit" className="buyer-button self-end">Search samples</button>
      </form>
      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">{samples.map(listing => <article key={listing.id} className="buyer-card overflow-hidden">
        <BuyerPhoto listing={listing} />
        <div className="grid gap-3 p-5"><p className="buyer-eyebrow">Sample inventory · Not for sale</p><h2 className="text-lg font-extrabold">{listing.title}</h2>
          <p className="text-xl font-bold text-primary">{new Intl.NumberFormat("en-NG", { style: "currency", currency: "NGN", maximumFractionDigits: 0 }).format(listing.price)}</p>
          <p className="buyer-muted text-sm">{listing.category} · {listing.location}</p>
          <Link href={`/demo/marketplace?${new URLSearchParams({ item: listing.id })}`} className="buyer-button">View sample item</Link>
        </div>
      </article>)}</div>
      {!samples.length && <p role="status" className="buyer-card p-8">No matching sample items. <Link href="/demo/marketplace" className="font-bold underline">Clear sample search</Link></p>}
    </>}
  </BuyerShell>;
}
