
import Link from "next/link";
import { notFound } from "next/navigation";
import { SiteHeader } from "@/components/layout/site-header";
import { ListingCard } from "@/components/marketplace/listing-card";
import { Container } from "@/components/ui/container";
import { Badge } from "@/components/ui/badge";
import { demoListings } from "@/lib/data/listings";

function makeVendorSlug(name: string) {
  return name.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

type VendorProfilePageProps = {
  params: Promise<{ slug: string }>;
};

export default async function VendorProfilePage({
  params,
}: VendorProfilePageProps) {
  const { slug } = await params;

  const vendorListings = demoListings.filter(
    (listing) => makeVendorSlug(listing.vendorName) === slug,
  );

  if (vendorListings.length === 0) {
    notFound();
  }

  const vendor = vendorListings[0];
  const activeListings = vendorListings.length;
  const verified = vendorListings.some((listing) => listing.verifiedVendor);

  const mapUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(vendor.location)}`;

  return (
    <>
      <SiteHeader />

      <main className="min-h-screen bg-background py-8 sm:py-12">
        <Container>
          <Link
            href="/marketplace"
            className="mb-6 inline-block text-sm font-medium text-primary hover:underline"
          >
            ← Back to marketplace
          </Link>

          <section className="rounded-2xl border border-border bg-white p-6 sm:p-8">
            <div className="flex flex-col gap-5 sm:flex-row sm:items-start">
              <div
                className="flex h-20 w-20 shrink-0 items-center justify-center rounded-full bg-background text-3xl"
                aria-hidden="true"
              >
                🏪
              </div>

              <div className="flex-1">
                <h1 className="text-2xl font-bold text-text">
                  {vendor.vendorName}
                </h1>

                <div className="mt-2">
                  {verified ? (
                    <Badge variant="success">Verified vendor</Badge>
                  ) : (
                    <Badge>Not verified</Badge>
                  )}
                </div>

                <p className="mt-3 text-sm text-muted">
                  📍 {vendor.location}
                </p>

                <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
                  Vendor profile and listings for buyers to explore before
                  making contact. Verification status is shown based on the
                  current demo listing data.
                </p>

                <div className="mt-5 flex flex-wrap gap-3">
                  <Link
                    href={`/listings/${vendor.id}`}
                    className="rounded-lg bg-primary px-4 py-3 text-center text-sm font-semibold text-white hover:opacity-90"
                  >
                    Contact vendor
                  </Link>

                  <a
                    href={mapUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="rounded-lg border border-border px-4 py-3 text-center text-sm font-semibold text-text hover:bg-background"
                  >
                    View area on map
                  </a>
                </div>
              </div>
            </div>
          </section>

          <section className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-xl border border-border bg-white p-5">
              <p className="text-sm text-muted">Listings in demo</p>
              <p className="mt-2 text-2xl font-bold text-text">
                {activeListings}
              </p>
            </div>

            <div className="rounded-xl border border-border bg-white p-5">
              <p className="text-sm text-muted">Vendor status</p>
              <p className="mt-2 text-lg font-bold text-text">
                {verified ? "Verified" : "Not verified"}
              </p>
            </div>

            <div className="rounded-xl border border-border bg-white p-5">
              <p className="text-sm text-muted">Rating / completed sales</p>
              <p className="mt-2 text-lg font-bold text-text">
                Not available yet
              </p>
              <p className="mt-1 text-xs text-muted">
                These metrics require vendor profile data.
              </p>
            </div>
          </section>

          <section className="mt-10">
            <h2 className="text-xl font-bold text-text">
              Listings from {vendor.vendorName}
            </h2>

            <p className="mt-2 text-sm text-muted">
              Browse the items this vendor has listed in the demo marketplace.
            </p>

            <div className="mt-5 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {vendorListings.map((listing) => (
                <ListingCard key={listing.id} listing={listing} />
              ))}
            </div>
          </section>
        </Container>
      </main>
    </>
  );
}
