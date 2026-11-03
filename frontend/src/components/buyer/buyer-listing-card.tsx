import Link from "next/link";
import { ListingPhoto } from "@/components/marketplace/listing-photo";
import type { BuyerListing } from "@/lib/data/buyer-fixtures";
import { BuyerIcon } from "./buyer-icon";
export function BuyerPhoto({
  listing,
  preferLegacy = false,
}: {
  listing: BuyerListing;
  preferLegacy?: boolean;
}) {
  // Unverified fixture image paths are never used as seller photographs.
  // The shared renderer always attempts the actual browser upload first.
  return (
    <ListingPhoto
      preferLegacy={preferLegacy}
      listingId={listing.id}
      category={listing.category}
      title={listing.title}
      className="aspect-[4/3] w-full rounded-[inherit]"
    />
  );
}

export function BuyerListingCard({
  listing,
  preferLegacy = false,
}: {
  listing: BuyerListing;
  preferLegacy?: boolean;
}) {
  const date = listing.createdAt.slice(0, 10);
  return (
    <article
      data-listing-id={listing.id}
      className="buyer-card group overflow-hidden transition hover:-translate-y-0.5 hover:shadow-lg"
    >
      <Link
        href={`/listings/${listing.id}`}
        aria-label={`View ${listing.title}`}
        className="block overflow-hidden"
      >
        <BuyerPhoto listing={listing} preferLegacy={preferLegacy} />
      </Link>
      <div className="grid gap-3 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span
            className={`rounded-full px-2.5 py-1 text-xs font-bold ${listing.condition === "Faulty" ? "bg-orange-50 text-orange-800" : "bg-emerald-50 text-emerald-800"}`}
          >
            {listing.condition}
          </span>
          <time dateTime={date} className="buyer-muted text-xs font-semibold">
            {new Intl.DateTimeFormat("en-GB", {
              day: "numeric",
              month: "short",
              year: "numeric",
              timeZone: "UTC",
            }).format(new Date(`${date}T00:00:00Z`))}
          </time>
        </div>
        <div>
          <h3 className="truncate text-base font-extrabold">{listing.title}</h3>
          <p className="mt-1 text-xl font-extrabold tracking-tight text-[#064829]">
            ₦{listing.price.toLocaleString("en-NG")}
            <span className="buyer-muted ml-1 text-xs font-medium">
              / {listing.unit}
            </span>
          </p>
        </div>
        <p className="buyer-muted flex items-center gap-1 text-xs font-semibold">
          <BuyerIcon name="pin" className="size-4" />
          {listing.location}
        </p>
        <p className="buyer-muted text-xs font-semibold">
          {listing.vendorName} · Sample vendor
        </p>
        <Link href={`/listings/${listing.id}`} className="buyer-button w-full">
          View item
        </Link>
      </div>
    </article>
  );
}
