"use client";
import { useMemo, useState, useSyncExternalStore } from "react";
import Image from "next/image";
import Link from "next/link";
import {
  buyerListings,
  vendorSlug,
  type BuyerListing,
} from "@/lib/data/buyer-fixtures";
import type { ScrapListing } from "@/lib/data/listings";
import type { VendorDemoListing } from "@/lib/data/vendor-listings";
import { ContactVendorForm } from "@/components/marketplace/contact-vendor-form";
import { BuyerIcon } from "./buyer-icon";
import { BuyerPhoto } from "./buyer-listing-card";
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

export function ListingDetails({ id, returnTo = "/marketplace" }: { id: string; returnTo?: string }) {
  const [activeImage, setActiveImage] = useState(0);
  const [notice, setNotice] = useState<"order" | "report" | null>(null);
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
    const sampleListing = buyerListings.find((item) => item.id === id);

    if (sampleListing) {
      return sampleListing as BuyerListing;
    }

    const vendorListing = vendorListings.find((item) => item.id === id);

    return vendorListing ? toScrapListing(vendorListing) : undefined;
  }, [id, vendorListings]);

  const isLoading = vendorListingsSnapshot === SERVER_SNAPSHOT;

  if (isLoading)
    return (
      <p role="status" className="buyer-muted">
        Loading listing details...
      </p>
    );
  if (!listing)
    return (
      <section className="buyer-card p-8 text-center">
        <h1 className="buyer-title">Listing not found</h1>
        <p className="buyer-muted mt-3">
          This listing is unavailable or is stored in a different browser.
        </p>
        <Link href={returnTo} className="buyer-button mt-6">
          Return to marketplace
        </Link>
      </section>
    );
  const item = listing as BuyerListing;
  const local = vendorListings.some((l) => l.id === item.id);
  const gallery = item.image
    ? [
        item.image,
        "/images/buyer/parts.jpg",
        "/images/buyer/mechanic.jpg",
        item.image,
      ]
    : [];
  const mapUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(item.location)}`;
  return (
    <>
      <Link
        href={returnTo}
        className="buyer-muted mb-5 inline-flex min-h-11 items-center gap-2 text-sm font-bold"
      >
        <BuyerIcon name="arrow" />
        Back to results
      </Link>
      <div className="grid gap-7 lg:grid-cols-[1.12fr_.88fr]">
        <section className="min-w-0">
          {gallery.length ? (
            <>
              <div className="relative aspect-[4/3] overflow-hidden rounded-3xl bg-slate-100">
                <Image
                  src={gallery[activeImage]}
                  alt={`${item.title} presentation gallery view ${activeImage + 1}`}
                  fill
                  sizes="(max-width:1023px) 100vw, 50vw"
                  className="object-cover"
                  preload
                />
              </div>
              <div className="mt-3 grid grid-cols-4 gap-3">
                {gallery.map((src, index) => (
                  <button
                    type="button"
                    key={index}
                    aria-label={`Show sample photo ${index + 1}`}
                    aria-pressed={activeImage === index}
                    onClick={() => setActiveImage(index)}
                    className={`relative aspect-square overflow-hidden rounded-xl border-2 ${activeImage === index ? "border-[#08783e]" : "border-transparent"}`}
                  >
                    <Image
                      src={src}
                      alt=""
                      fill
                      sizes="(max-width:1023px) 22vw, 12vw"
                      className="object-cover"
                    />
                  </button>
                ))}
              </div>
              <p className="buyer-muted mt-3 text-xs">
                Presentation gallery · Sample images from the designer, not
                evidence of an available item.
              </p>
            </>
          ) : (
            <div className="overflow-hidden rounded-3xl">
              <BuyerPhoto listing={item} />
            </div>
          )}
        </section>
        <section className="min-w-0 lg:pl-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-800">
              {item.condition}
            </span>
            <span className="buyer-muted text-xs font-semibold">
              {local ? "Browser-local demo listing" : "Presentation fixture"}
            </span>
          </div>
          <h1 className="mt-4 text-4xl font-extrabold tracking-tight">
            {item.title}
          </h1>
          <p className="mt-3 text-3xl font-extrabold text-[#064829]">
            {formatPrice(item.price)}
            <span className="buyer-muted ml-1 text-sm font-medium">
              / {item.unit}
            </span>
          </p>
          <p className="buyer-muted mt-3 flex items-center gap-2 text-sm font-semibold">
            <BuyerIcon name="pin" />
            {item.location}
          </p>
          <div className="buyer-card mt-6 p-5">
            {local ? (
              <>
                <h2 className="text-lg font-extrabold">{item.vendorName}</h2>
                <p className="buyer-muted mt-2 text-xs">
                  Browser-local shop · public vendor profile not connected.
                </p>
              </>
            ) : (
              <Link
                href={`/vendors/${vendorSlug(item.vendorName)}`}
                className="flex items-center gap-4"
              >
                <span className="buyer-dark grid size-12 shrink-0 place-items-center rounded-full font-bold text-white">
                  {item.vendorName
                    .split(" ")
                    .map((w) => w[0])
                    .slice(0, 2)
                    .join("")}
                </span>
                <span>
                  <span className="block text-lg font-extrabold">
                    {item.vendorName}
                  </span>
                  <span className="buyer-muted mt-1 block text-xs font-semibold">
                    Sample vendor · No live rating or verification
                  </span>
                </span>
                <BuyerIcon
                  name="chevron"
                  className="buyer-muted ml-auto size-5 shrink-0"
                />
              </Link>
            )}
          </div>
          <div className="buyer-soft mt-6 rounded-2xl p-5">
            <p className="buyer-eyebrow">Payment method</p>
            <h2 className="mt-1 text-xl font-extrabold">Pay on Delivery</h2>
            <p className="buyer-muted mt-1 text-sm">
              Intended policy: inspect before paying. This demo does not process
              orders or payments.
            </p>
          </div>
          <div className="mt-6 grid gap-3 sm:grid-cols-2">
            <a href="#contact-vendor" className="buyer-button sm:col-span-2">
              <BuyerIcon name="message" />
              Contact vendor
            </a>
            <button
              type="button"
              onClick={() => setNotice("order")}
              className="buyer-button buyer-ghost"
            >
              <BuyerIcon name="bag" />
              Order item
            </button>
            <a
              href={mapUrl}
              target="_blank"
              rel="noreferrer"
              className="buyer-button buyer-ghost"
            >
              <BuyerIcon name="pin" />
              View location
            </a>
          </div>
          {notice && (
            <div
              role="status"
              className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"
            >
              <p>
                {notice === "order"
                  ? "Sample interaction only. No real order, reservation or payment has been created."
                  : "Reporting is not connected. No report was submitted or saved."}
              </p>
              <button
                type="button"
                className="mt-2 font-bold underline"
                onClick={() => setNotice(null)}
              >
                Dismiss
              </button>
            </div>
          )}
          <div className="mt-7 border-t border-[#dfe6e1] pt-6">
            <h2 className="text-xl font-extrabold">Item details</h2>
            <p className="buyer-muted mt-3 text-sm leading-relaxed">
              {item.description}
            </p>
            <dl className="mt-5 grid gap-4 text-sm sm:grid-cols-2">
              <div>
                <dt className="buyer-muted">Available quantity</dt>
                <dd className="mt-1 font-semibold">{item.quantity}</dd>
              </div>
              <div>
                <dt className="buyer-muted">Category</dt>
                <dd className="mt-1 font-semibold">{item.category}</dd>
              </div>
            </dl>
            <button
              type="button"
              onClick={() => setNotice("report")}
              className="mt-5 min-h-11 text-sm font-bold text-red-700"
            >
              Report this listing
            </button>
          </div>
        </section>
      </div>
      <div id="contact-vendor" className="mt-7 max-w-3xl">
        <ContactVendorForm
          vendorName={item.vendorName}
          listingTitle={item.title}
        />
      </div>
    </>
  );
}
