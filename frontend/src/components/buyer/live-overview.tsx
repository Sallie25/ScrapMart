import Image from "next/image";
import Link from "next/link";
import type { CatalogueCategory, CatalogueListing } from "@/lib/marketplace/catalogue";
import { conditions, formatMoney, priceBasis } from "@/lib/marketplace/catalogue";

export function LiveCategoryGrid({ categories }: { categories: CatalogueCategory[] }) {
  return <div className="mt-5 grid grid-cols-3 gap-3 sm:grid-cols-5 lg:grid-cols-11">
    {categories.map(category => <Link key={category.id} href={`/marketplace?category_id=${category.id}`}
      className="group min-w-0 overflow-hidden rounded-2xl border border-[#dfe6e1] bg-white p-4 text-center transition hover:border-[#08783e]/40 hover:shadow-lg">
      <span className="block break-words text-xs font-bold">{category.name}</span>
    </Link>)}
  </div>;
}

export function LiveBuyerListingCard({ listing }: { listing: CatalogueListing }) {
  return <article data-listing-id={listing.id} className="buyer-card group overflow-hidden transition hover:-translate-y-0.5 hover:shadow-lg">
    <Link href={`/listings/${listing.id}`} aria-label={`View ${listing.title}`} className="block overflow-hidden">
      <Image unoptimized src={listing.photos[0].url} alt={listing.title} width={listing.photos[0].width ?? 800}
        height={listing.photos[0].height ?? 600} className="aspect-[4/3] w-full object-cover" />
    </Link>
    <div className="grid gap-3 p-4"><div className="flex flex-wrap items-center justify-between gap-2">
      <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-bold text-emerald-800">{conditions[listing.condition]}</span>
      <time dateTime={listing.published_at} className="buyer-muted text-xs font-semibold">{new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(listing.published_at))}</time>
    </div><div><h3 className="truncate text-base font-extrabold">{listing.title}</h3><p className="mt-1 text-xl font-extrabold tracking-tight text-[#064829]">{formatMoney(listing.price)}<span className="buyer-muted ml-1 text-xs font-medium">{priceBasis(listing)}</span></p></div>
    <p className="buyer-muted text-xs font-semibold">{listing.location_summary}</p><p className="buyer-muted text-xs font-semibold">{listing.vendor.business_name} · Verified vendor</p>
    <Link href={`/listings/${listing.id}`} className="buyer-button w-full">View item</Link></div>
  </article>;
}
