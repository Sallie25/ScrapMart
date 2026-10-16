
"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useSyncExternalStore } from "react";
import { SiteHeader } from "@/components/layout/site-header";
import { Container } from "@/components/ui/container";
import { Badge } from "@/components/ui/badge";
import { ContactVendorForm } from "@/components/marketplace/contact-vendor-form";
import { ListingPhoto } from "@/components/marketplace/listing-photo";
import { demoListings, type ScrapListing } from "@/lib/data/listings";
import type { VendorDemoListing } from "@/lib/data/vendor-listings";

const STORAGE_KEY = "scrapmart-vendor-demo-listings";
const UPDATE_EVENT = "scrapmart-demo-listings-updated";
const SERVER_SNAPSHOT = "__scrapmart_server_snapshot__";

function subscribeToVendorListings(onChange: () => void) {
  window.addEventListener(UPDATE_EVENT, onChange);
  window.addEventListener("storage", onChange);

  return () => {
    window.removeEventListener(UPDATE_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

function getVendorListingsSnapshot(): string {
  try {
    return window.localStorage.getItem(STORAGE_KEY) ?? "[]";
  } catch {
    return "[]";
  }
}

function getServerSnapshot(): string {
  return SERVER_SNAPSHOT;
}

function parseVendorListings(snapshot: string): VendorDemoListing[] {
  try {
    const parsed: unknown = JSON.parse(snapshot);

    if (!Array.isArray(parsed)) {
      return [];
    }

    return parsed as VendorDemoListing[];
  } catch {
    return [];
  }
}

function toScrapListing(listing: VendorDemoListing): ScrapListing {
  return {
    id: listing.id,
    title: listing.title,
    category: listing.category,
    price: listing.price,
    unit: listing.unit,
    condition: listing.condition,
    location: listing.location,
    vendorName: listing.vendorName?.trim() || "Your Demo Shop",
    verifiedVendor: false,
    quantity: `${listing.quantity} ${listing.unit}${listing.quantity === 1 ? "" : "s"}`,
    description: listing.description,
    createdAt: listing.createdAt,
  };
}

function formatPrice(price: number) {
  return new Intl.NumberFormat("en-NG", {
    style: "currency",
    currency: "NGN",
    maximumFractionDigits: 0,
  }).format(price);
}

function makeVendorSlug(name: string) {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

export default function ListingDetailsPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const vendorListingsSnapshot = useSyncExternalStore(
    subscribeToVendorListings,
    getVendorListingsSnapshot,
    getServerSnapshot,
  );

  const vendorListings = useMemo(
    () => parseVendorListings(vendorListingsSnapshot),
    [vendorListingsSnapshot],
  );

  const listing = useMemo(() => {
    const sampleListing = demoListings.find((item) => item.id === id);

    if (sampleListing) {
      return sampleListing;
    }

    const vendorListing = vendorListings.find((item) => item.id === id);

    return vendorListing ? toScrapListing(vendorListing) : undefined;
  }, [id, vendorListings]);

  const isLoading = vendorListingsSnapshot === SERVER_SNAPSHOT;

  if (isLoading) {
    return (
      <>
        <SiteHeader />
        <main className="min-h-screen bg-background py-12">
          <Container>
            <p className="text-muted" role="status">
              Loading listing details...
            </p>
          </Container>
        </main>
      </>
    );
  }

  if (!listing) {
    return (
      <>
        <SiteHeader />
        <main className="min-h-screen bg-background py-12">
          <Container>
            <div className="rounded-2xl border border-border bg-white p-8 text-center">
              <h1 className="text-2xl font-bold text-text">
                Listing not found
              </h1>
              <p className="mt-3 text-muted">
                This listing may have been removed or is not available in this
                browser.
              </p>
              <Link
                href="/marketplace"
                className="mt-6 inline-block rounded-lg bg-primary px-5 py-3 font-semibold text-white hover:opacity-90"
              >
                Return to marketplace
              </Link>
            </div>
          </Container>
        </main>
      </>
    );
  }

  const isVendorDemoListing = vendorListings.some(
    (item) => item.id === listing.id,
  );

  const vendorSlug = makeVendorSlug(listing.vendorName);
  const mapUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(listing.location)}`;

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

          <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
            <section className="space-y-6 lg:col-span-2">
              <ListingPhoto
                listingId={listing.id}
                category={listing.category}
                title={listing.title}
                className="min-h-64 aspect-[4/3] rounded-2xl border border-border bg-white sm:aspect-[16/9]"
              />

              <div className="rounded-2xl border border-border bg-white p-6 sm:p-8">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge>{listing.category}</Badge>
                  <Badge>{listing.condition}</Badge>
                  {listing.verifiedVendor ? (
                    <Badge variant="success">Verified vendor</Badge>
                  ) : (
                    <Badge>Not verified</Badge>
                  )}
                  {isVendorDemoListing && <Badge>Browser demo listing</Badge>}
                </div>

                <h1 className="mt-4 text-2xl font-bold text-text sm:text-3xl">
                  {listing.title}
                </h1>

                <p className="mt-4 text-2xl font-bold text-primary">
                  {formatPrice(listing.price)}
                  <span className="ml-1 text-base font-medium text-muted">
                    / {listing.unit}
                  </span>
                </p>

                <div className="mt-6 grid grid-cols-1 gap-4 border-y border-border py-5 sm:grid-cols-2">
                  <div>
                    <p className="text-sm text-muted">Available quantity</p>
                    <p className="mt-1 font-semibold text-text">
                      {listing.quantity}
                    </p>
                  </div>

                  <div>
                    <p className="text-sm text-muted">Location</p>
                    <p className="mt-1 font-semibold text-text">
                      {listing.location}
                    </p>
                  </div>

                  <div>
                    <p className="text-sm text-muted">Condition</p>
                    <p className="mt-1 font-semibold text-text">
                      {listing.condition}
                    </p>
                  </div>

                  <div>
                    <p className="text-sm text-muted">Payment method</p>
                    <p className="mt-1 font-semibold text-text">
                      Pay on delivery
                    </p>
                  </div>
                </div>

                <h2 className="mt-6 text-lg font-bold text-text">
                  Description
                </h2>
                <p className="mt-2 leading-7 text-muted">
                  {listing.description}
                </p>
              </div>
            </section>

            <aside className="space-y-5">
              <div className="rounded-2xl border border-border bg-white p-6">
                <h2 className="text-lg font-bold text-text">
                  Vendor information
                </h2>

                <p className="mt-4 font-semibold text-text">
                  {listing.vendorName}
                </p>

                <p className="mt-2 text-sm text-muted">
                  📍 {listing.location}
                </p>

                <div className="mt-3">
                  {listing.verifiedVendor ? (
                    <Badge variant="success">Verified vendor</Badge>
                  ) : (
                    <Badge>Not verified</Badge>
                  )}
                </div>

                {isVendorDemoListing ? (
                  <p className="mt-5 text-sm leading-6 text-muted">
                    This is a local prototype listing. A public vendor profile
                    will be available when vendor accounts are connected to the
                    backend.
                  </p>
                ) : (
                  <Link
                    href={`/vendors/${vendorSlug}`}
                    className="mt-5 block rounded-lg border border-border px-4 py-3 text-center text-sm font-semibold text-text hover:bg-background"
                  >
                    View vendor profile
                  </Link>
                )}

                <a
                  href={mapUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-3 block rounded-lg border border-border px-4 py-3 text-center text-sm font-semibold text-text hover:bg-background"
                >
                  View location on map
                </a>
              </div>

              <ContactVendorForm
                vendorName={listing.vendorName}
                listingTitle={listing.title}
              />

              <div className="rounded-2xl border border-border bg-white p-6">
                <h2 className="font-bold text-text">Buying safely</h2>
                <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-6 text-muted">
                  <li>Inspect the material before agreeing to buy.</li>
                  <li>Confirm the quantity and final price with the vendor.</li>
                  <li>Use pay on delivery; do not send advance payment.</li>
                  <li>Arrange collection details directly with the vendor.</li>
                </ul>
              </div>
            </aside>
          </div>
        </Container>
      </main>
    </>
  );
}
