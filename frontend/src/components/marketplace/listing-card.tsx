
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import type { ScrapListing } from "@/lib/data/listings";

type ListingCardProps = {
  listing: ScrapListing;
};

export function ListingCard({ listing }: ListingCardProps) {
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
        <div
          className="flex aspect-[4/3] items-center justify-center bg-background"
          aria-hidden="true"
        >
          <div className="text-center">
            <div className="text-4xl">
              {listing.category === "Metals"
                ? "🔩"
                : listing.category === "Plastics"
                  ? "♻️"
                  : listing.category === "Paper"
                    ? "📦"
                    : "⚙️"}
            </div>
            <p className="mt-2 text-xs text-muted">
              {listing.category}
            </p>
          </div>
        </div>

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