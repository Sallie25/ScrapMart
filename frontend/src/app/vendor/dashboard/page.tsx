
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { SiteHeader } from "@/components/layout/site-header";
import {
  deleteVendorDemoListing,
  getVendorDemoListings,
  type VendorDemoListing,
} from "@/lib/data/vendor-listings";

const sampleListings = [
  {
    title: "Clean Aluminium Scrap",
    category: "Metals",
    price: "₦3,200/kg",
    status: "Sample",
  },
  {
    title: "Used Plastic Bottles",
    category: "Plastics",
    price: "₦450/kg",
    status: "Sample",
  },
];

export default function VendorDashboardPage() {
  const [listings, setListings] = useState<VendorDemoListing[]>(() => []);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const refreshListings = () => {
      setListings(getVendorDemoListings());
      setReady(true);
    };

    // Load browser-local listings after the component mounts.
    refreshListings();

    window.addEventListener(
      "scrapmart-demo-listings-updated",
      refreshListings,
    );
    window.addEventListener("storage", refreshListings);

    return () => {
      window.removeEventListener(
        "scrapmart-demo-listings-updated",
        refreshListings,
      );
      window.removeEventListener("storage", refreshListings);
    };
  }, []);

  function handleDelete(id: string, title: string) {
    const confirmed = window.confirm(
      `Remove "${title}" from this browser's demo listings?`,
    );

    if (confirmed) {
      deleteVendorDemoListing(id);
    }
  }

  return (
    <>
      <SiteHeader />

      <main className="mx-auto max-w-screen-xl px-4 py-10 sm:px-6 lg:px-8">
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
          <div>
            <p className="text-sm font-medium text-primary">
              SELLER WORKSPACE
            </p>
            <h1 className="mt-2 text-3xl font-bold tracking-tight text-text">
              Vendor dashboard
            </h1>
            <p className="mt-2 text-muted">
              Manage your shop and the scrap materials you offer.
            </p>
          </div>

          <Link
            href="/vendor/listings/new"
            className="inline-flex items-center justify-center rounded-md bg-primary px-5 py-3 font-medium text-white transition-colors hover:bg-primary-hover"
          >
            + Create listing
          </Link>
        </div>

        <section
          aria-label="Shop verification status"
          className="mt-8 rounded-xl border border-amber-300 bg-amber-50 p-5"
        >
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
            <div>
              <h2 className="font-semibold text-amber-950">
                Vendor verification required
              </h2>
              <p className="mt-1 text-sm leading-6 text-amber-900">
                Identity verification is not connected in this prototype.
                This demo status does not represent a real verification check.
              </p>
            </div>
            <span className="w-fit rounded-full border border-amber-300 px-3 py-1 text-xs font-semibold text-amber-900">
              Not verified
            </span>
          </div>
        </section>

        <section
          aria-label="Shop overview"
          className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
        >
          <div className="rounded-xl border border-border bg-surface p-5">
            <p className="text-sm text-muted">Your demo listings</p>
            <p className="mt-2 text-3xl font-bold text-text">
              {ready ? listings.length : "—"}
            </p>
            <p className="mt-1 text-sm text-muted">
              Saved in this browser
            </p>
          </div>

          <div className="rounded-xl border border-border bg-surface p-5">
            <p className="text-sm text-muted">Shop location</p>
            <p className="mt-2 text-xl font-bold text-text">Lagos, Nigeria</p>
            <p className="mt-1 text-sm text-muted">
              Example location; shop profile is not connected
            </p>
          </div>

          <div className="rounded-xl border border-border bg-surface p-5">
            <p className="text-sm text-muted">Orders</p>
            <p className="mt-2 text-3xl font-bold text-text">0</p>
            <p className="mt-1 text-sm text-muted">
              Order data is not connected yet
            </p>
          </div>
        </section>

        <section className="mt-10">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-xl font-bold text-text">
                Your demo listings
              </h2>
              <p className="mt-1 text-sm text-muted">
                Listings created here are stored only in this browser.
              </p>
            </div>

            <Link
              href="/vendor/listings/new"
              className="text-sm font-semibold text-primary hover:underline"
            >
              Add a material
            </Link>
          </div>

          <div className="mt-4 overflow-hidden rounded-xl border border-border">
            {!ready ? (
              <p className="p-5 text-sm text-muted">
                Loading your demo listings...
              </p>
            ) : listings.length === 0 ? (
              <div className="p-6 text-center">
                <h3 className="font-semibold text-text">
                  No demo listings created yet
                </h3>
                <p className="mt-2 text-sm text-muted">
                  Create a listing to see it appear here.
                </p>
                <Link
                  href="/vendor/listings/new"
                  className="mt-4 inline-flex rounded-md bg-primary px-4 py-2 font-medium text-white hover:bg-primary-hover"
                >
                  Create your first listing
                </Link>
              </div>
            ) : (
              listings.map((listing) => (
                <article
                  key={listing.id}
                  className="flex flex-col justify-between gap-4 border-b border-border p-4 last:border-b-0 sm:flex-row sm:items-center"
                >
                  <div className="min-w-0">
                    <h3 className="font-semibold text-text">
                      {listing.title}
                    </h3>
                    <p className="mt-1 text-sm text-muted">
                      {listing.category} · {listing.condition} ·{" "}
                      {listing.quantity.toLocaleString("en-NG")} {listing.unit}
                    </p>
                    <p className="mt-1 text-sm text-muted">
                      📍 {listing.location}
                    </p>
                    {listing.photoName && (
                      <p className="mt-1 truncate text-xs text-muted">
                        Selected photo: {listing.photoName}
                      </p>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center gap-3 sm:justify-end">
                    <span className="font-semibold text-primary">
                      ₦{listing.price.toLocaleString("en-NG")}/{listing.unit}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleDelete(listing.id, listing.title)}
                      className="rounded-md border border-red-200 px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-50"
                    >
                      Remove
                    </button>
                  </div>
                </article>
              ))
            )}
          </div>
        </section>

        <section className="mt-8">
          <h2 className="text-xl font-bold text-text">
            Example marketplace listings
          </h2>
          <p className="mt-1 text-sm text-muted">
            These are illustrative examples, not listings owned by your shop.
          </p>

          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            {sampleListings.map((listing) => (
              <div
                key={listing.title}
                className="rounded-xl border border-border bg-surface p-5"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="font-semibold text-text">
                      {listing.title}
                    </h3>
                    <p className="mt-1 text-sm text-muted">
                      {listing.category}
                    </p>
                  </div>
                  <span className="rounded-full bg-background px-3 py-1 text-xs text-muted">
                    {listing.status}
                  </span>
                </div>
                <p className="mt-3 font-semibold text-primary">
                  {listing.price}
                </p>
              </div>
            ))}
          </div>
        </section>

        <section className="mt-8 rounded-xl border border-border bg-surface p-5">
          <h2 className="font-semibold text-text">Selling safely</h2>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-6 text-muted">
            <li>Keep your listing descriptions and prices accurate.</li>
            <li>Agree on collection and delivery details with the buyer.</li>
            <li>ScrapMart&apos;s MVP uses pay-on-delivery.</li>
            <li>Never claim verification until it has actually been completed.</li>
          </ul>
        </section>
      </main>
    </>
  );
}
