
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { ListingPhoto } from "@/components/marketplace/listing-photo";
import type { ScrapListing } from "@/lib/data/listings";

type ListingCardProps = {
  listing: ScrapListing;
  variant?: "default" | "marketplace";
};

export function ListingCard({ listing, variant = "default" }: ListingCardProps) {
  if (variant === "marketplace") {
    // Calendar dates avoid a clock-dependent relative label and timezone shifts.
    const calendarDate = listing.createdAt.slice(0, 10);
    const dateLabel = new Intl.DateTimeFormat("en-GB", {
      day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
    }).format(new Date(`${calendarDate}T00:00:00Z`));

    return (
      <article className="overflow-hidden rounded-2xl border border-[#dce4df] bg-white shadow-sm transition-shadow hover:shadow-md">
        <Link href={`/listings/${listing.id}`} aria-label={`View ${listing.title}`}
          className="flex h-full flex-col rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#087b40]">
          <ListingPhoto listingId={listing.id} category={listing.category} title={listing.title} className="aspect-[4/3] shrink-0 bg-[#edf2ef]" />
          <div className="flex flex-1 flex-col gap-3 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${listing.condition === "Faulty" ? "bg-orange-50 text-orange-800" : "bg-[#ecfbf5] text-[#006b52]"}`}>
                <span aria-hidden="true">●</span>{listing.condition}
              </span>
              <time dateTime={calendarDate} className="text-xs text-[#63736c]">{dateLabel}</time>
            </div>
            <h2 className="text-base font-bold leading-6 text-[#15221b]">{listing.title}</h2>
            <p className="text-xl font-bold text-[#064d31]">
              ₦{listing.price.toLocaleString("en-NG")}<span className="ml-1 text-sm font-normal text-[#63736c]">/ {listing.unit}</span>
            </p>
            <p className="text-sm text-[#63736c]"><span aria-hidden="true">⌖ </span>{listing.location}</p>
            {listing.verifiedVendor && <p className="text-xs font-semibold text-[#007b56]"><span aria-hidden="true">✓ </span>Verified vendor</p>}
            <p className="text-xs leading-5 text-[#63736c]">{listing.vendorName} · {listing.quantity}</p>
            <span className="mt-auto inline-flex min-h-12 items-center justify-center rounded-xl bg-[#087b40] px-4 py-3 text-sm font-medium text-white">View item</span>
          </div>
        </Link>
      </article>
    );
  }

  return (
    <Card
      padding="none"
      className="overflow-hidden transition-shadow hover:shadow-md"
    >
      <Link
        href={`/listings/${listing.id}`}
        className="block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        aria-label={`View ${listing.title}`}
      >
        <ListingPhoto
          listingId={listing.id}
          category={listing.category}
          title={listing.title}
          className="aspect-[4/3] bg-background"
        />

        <div className="space-y-3 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge>{listing.condition}</Badge>
            <Badge variant="info">{listing.category}</Badge>
          </div>

          <h2 className="line-clamp-2 font-semibold text-text">
            {listing.title}
          </h2>

          <p className="text-xl font-bold text-primary">
            ₦{listing.price.toLocaleString("en-NG")}
            <span className="ml-1 text-sm font-normal text-muted">
              / {listing.unit}
            </span>
          </p>

          <p className="text-sm text-muted">
            📍 {listing.location}
          </p>

          <div className="border-t border-border pt-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm text-text">
                {listing.vendorName}
              </span>

              {listing.verifiedVendor && (
                <Badge variant="success">Verified vendor</Badge>
              )}
            </div>

            <p className="mt-2 text-xs text-muted">
              {listing.quantity}
            </p>
          </div>
        </div>
      </Link>
    </Card>
  );
}
