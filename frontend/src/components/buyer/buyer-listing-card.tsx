import Image from "next/image";
import Link from "next/link";
import { ListingPhoto } from "@/components/marketplace/listing-photo";
import type { BuyerListing } from "@/lib/data/buyer-fixtures";
import { BuyerIcon } from "./buyer-icon";
export function BuyerPhoto({ listing }: { listing: BuyerListing }) {
  const illustration = (
    {
      Metals: "/images/category-metals.jpg",
      Plastics: "/images/category-plastics.jpg",
      Electronics: "/images/category-electronics.jpg",
    } as Record<string, string>
  )[listing.category];
  return (
    <div className="relative aspect-[4/3] overflow-hidden rounded-[inherit] bg-[#edf2ef]">
      {listing.image ? (
        <Image
          src={listing.image}
          alt={`${listing.title} — presentation image`}
          fill
          sizes="(max-width:640px) 100vw, (max-width:1024px) 50vw, 30vw"
          className="object-cover"
        />
      ) : (
        <>
          {illustration && (
            <Image
              src={illustration}
              alt={`${listing.category} category illustration, not this item`}
              fill
              sizes="(max-width:640px) 100vw, 30vw"
              className="object-cover"
            />
          )}
          <ListingPhoto
            listingId={listing.id}
            category={listing.category}
            title={listing.title}
            className={`peer aspect-[4/3] w-full ${illustration ? "[&>div]:hidden" : ""}`}
          />
        </>
      )}
      <span className="absolute bottom-2 left-2 rounded-full bg-white/95 px-2 py-1 text-[10px] font-bold text-[#14211a] peer-has-[img]:hidden">
        {listing.image
          ? "Presentation image"
          : illustration
            ? "Category illustration"
            : "Photo unavailable"}
      </span>
    </div>
  );
}
export function BuyerListingCard({ listing }: { listing: BuyerListing }) {
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
        <BuyerPhoto listing={listing} />
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
