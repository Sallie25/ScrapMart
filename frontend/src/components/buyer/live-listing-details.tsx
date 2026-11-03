import Link from "next/link";
import { BuyerIcon } from "./buyer-icon";
import { LiveListingGallery } from "./live-listing-gallery";
import { conditions, formatMoney, formatQuantity, priceBasis, units } from "@/lib/marketplace/catalogue";
import type { CatalogueListing } from "@/lib/marketplace/catalogue";
import { publicLocation } from "@/lib/marketplace/detail";

export function LiveListingDetails({ listing, returnTo }: { listing: CatalogueListing; returnTo: string }) {
  const location = publicLocation(listing);
  return <>
    <Link href={returnTo} className="buyer-muted mb-5 inline-flex min-h-11 items-center gap-2 text-sm font-bold"><BuyerIcon name="arrow" />Back to results</Link>
    <div className="grid gap-7 lg:grid-cols-[1.12fr_.88fr]">
      <LiveListingGallery listing={listing} />
      <section className="min-w-0 lg:pl-4">
        <div className="flex flex-wrap items-center gap-2"><span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-800">{conditions[listing.condition]}</span><span className="buyer-muted text-xs font-semibold">Live listing</span></div>
        <h1 className="mt-4 text-4xl font-extrabold tracking-tight">{listing.title}</h1>
        <p className="mt-3 text-3xl font-extrabold text-[#064829]">{formatMoney(listing.price)}<span className="buyer-muted ml-1 text-sm font-medium">{priceBasis(listing)}</span></p>
        {listing.is_negotiable && <p className="buyer-muted mt-2 text-sm font-semibold">Price negotiable</p>}
        <p className="buyer-muted mt-3 flex items-center gap-2 text-sm font-semibold"><BuyerIcon name="pin" />{location.summary}</p>
        <div className="buyer-card mt-6 p-5"><h2 className="text-lg font-extrabold">{listing.vendor.business_name}</h2><p className="buyer-muted mt-2 text-xs">Verified vendor · Public listing location: {listing.vendor.shop_location}</p></div>
        <div className="buyer-soft mt-6 rounded-2xl p-5"><p className="buyer-eyebrow">Buying this item</p><h2 className="mt-1 text-xl font-extrabold">Contact and ordering</h2><p className="buyer-muted mt-1 text-sm">Contact and ordering are not connected for live listings yet. No message, order or payment can be submitted here.</p></div>
        {location.directionsUrl && <a href={location.directionsUrl} target="_blank" rel="noreferrer" className="buyer-button buyer-ghost mt-6"><BuyerIcon name="pin" />View public site</a>}
        <div className="mt-7 border-t border-[#dfe6e1] pt-6"><h2 className="text-xl font-extrabold">Item details</h2><p className="buyer-muted mt-3 whitespace-pre-wrap text-sm leading-relaxed">{listing.description}</p><dl className="mt-5 grid gap-4 text-sm sm:grid-cols-2"><div><dt className="buyer-muted">Available quantity</dt><dd className="mt-1 font-semibold">{formatQuantity(listing.available_quantity)} {units[listing.quantity_unit]}{listing.quantity_unit === "pieces" && listing.available_quantity !== "1.000" ? "s" : ""}</dd></div><div><dt className="buyer-muted">Category</dt><dd className="mt-1 font-semibold">{listing.category.name}</dd></div><div><dt className="buyer-muted">Condition</dt><dd className="mt-1 font-semibold">{conditions[listing.condition]}</dd></div><div><dt className="buyer-muted">Listed quantity</dt><dd className="mt-1 font-semibold">{formatQuantity(listing.quantity)} {units[listing.quantity_unit]}</dd></div></dl></div>
      </section>
    </div>
  </>;
}
