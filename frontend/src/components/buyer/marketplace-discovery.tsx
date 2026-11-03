"use client";
import { useState, useTransition, type FormEvent, type ReactNode } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { BuyerIcon } from "./buyer-icon";
import { conditions, formatMoney, formatQuantity, priceBasis } from "@/lib/marketplace/catalogue";
import type { MarketplaceView } from "@/lib/server/marketplace/page-data";
import { catalogueHref, listingHref } from "@/lib/marketplace/query";
import type { CatalogueQuery } from "@/lib/marketplace/query";

function FilterSelect({ id, label, value, onChange, children }: {
  id: string; label: string; value: string; onChange: (value: string) => void; children: ReactNode;
}) {
  return <label htmlFor={id} className="grid gap-2 text-sm font-bold">{label}<select id={id} value={value} onChange={event => onChange(event.target.value)}>{children}</select></label>;
}
export function MarketplaceDiscovery({ categories, query, page, error }: MarketplaceView) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [search, setSearch] = useState(query.q ?? "");
  const [location, setLocation] = useState(query.location ?? "");
  const [minPrice, setMinPrice] = useState(query.min_price ?? "");
  const [maxPrice, setMaxPrice] = useState(query.max_price ?? "");
  const [inputError, setInputError] = useState("");
  const navigate = (changes: Partial<CatalogueQuery>, resetCursor = true) => {
    const next = { ...query, ...changes };
    if (resetCursor) delete next.cursor;
    startTransition(() => router.push(catalogueHref(next)));
  };
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (minPrice && maxPrice && Number(minPrice) > Number(maxPrice)) {
      setInputError("Minimum price cannot be greater than maximum price."); return;
    }
    setInputError("");
    navigate({ q: search.trim(), location: location.trim(), min_price: minPrice, max_price: maxPrice });
  };
  const clearFilters = () => { setSearch(""); setLocation(""); setMinPrice(""); setMaxPrice(""); setInputError(""); startTransition(() => router.push("/marketplace")); };
  const count = page?.listings.length ?? 0;
  return <>
    <Link href="/" className="buyer-muted mb-5 inline-flex min-h-11 items-center gap-2 text-sm font-bold"><BuyerIcon name="arrow" />Back to home</Link>
    <div className="flex items-end justify-between gap-4"><div><p className="buyer-eyebrow">Marketplace</p><h1 className="buyer-title">Find scrap</h1></div><p className="buyer-muted text-sm font-bold">{page ? `${count} listings on this page` : "Live catalogue"}</p></div>
    <form onSubmit={submit} className="mt-5 flex flex-wrap gap-2 rounded-2xl border border-[#dfe6e1] bg-white p-2 shadow-sm">
      <label htmlFor="listing-search" className="sr-only">Search scrap materials</label><span className="buyer-muted grid size-11 place-items-center"><BuyerIcon name="search" /></span>
      <input id="listing-search" type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Try engine or copper" className="min-w-0 flex-1 font-semibold" />
      <button type="submit" className="buyer-button max-sm:w-full" disabled={pending}>Search</button>
    </form>
    <div className="mt-6 grid gap-6 lg:grid-cols-[16rem_1fr]">
      <aside className="buyer-card h-fit p-5"><div className="flex items-center justify-between"><h2 className="text-lg font-extrabold">Filters</h2><BuyerIcon name="filter" /></div>
        <form onSubmit={submit} className="mt-5 grid gap-5">
          <FilterSelect id="listing-category" label="Category" value={query.category_id ?? ""} onChange={value => navigate({ category_id: value })}>
            <option value="">All categories</option>{categories.map(category => <option key={category.id} value={category.id}>{category.name}</option>)}
          </FilterSelect>
          <label htmlFor="listing-location" className="grid gap-2 text-sm font-bold">Location<input id="listing-location" value={location} onChange={event => setLocation(event.target.value)} placeholder="Town, LGA or area" maxLength={100} /></label>
          <FilterSelect id="listing-condition" label="Condition" value={query.condition ?? ""} onChange={value => navigate({ condition: value as CatalogueQuery["condition"] })}>
            <option value="">All conditions</option>{Object.entries(conditions).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </FilterSelect>
          <fieldset><legend className="mb-2 text-sm font-bold">Price range (₦)</legend><div className="grid gap-3">
            <label htmlFor="minimum-price" className="grid gap-1 text-xs font-semibold">Minimum price<input id="minimum-price" type="number" min="0" max="999999999999.99" step="0.01" value={minPrice} onChange={event => setMinPrice(event.target.value)} placeholder="e.g. 300" /></label>
            <label htmlFor="maximum-price" className="grid gap-1 text-xs font-semibold">Maximum price<input id="maximum-price" type="number" min="0" max="999999999999.99" step="0.01" value={maxPrice} onChange={event => setMaxPrice(event.target.value)} placeholder="e.g. 5000" /></label>
          </div></fieldset>
          {inputError && <p role="alert" className="text-sm text-red-700">{inputError}</p>}
          <button type="submit" className="buyer-button" disabled={pending}>Apply filters</button>
          <button type="button" onClick={clearFilters} className="buyer-button buyer-ghost">Clear filters</button>
        </form>
      </aside>
      <section className="min-w-0" aria-busy={pending}>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><h2 id="marketplace-results" tabIndex={-1} className="buyer-muted text-sm font-bold" aria-live="polite">{pending ? "Loading listings…" : page ? `Showing ${count} live listings` : "Marketplace listings"}</h2><span className="buyer-muted text-sm font-bold">Newest first</span></div>
        {error ? <div role="alert" className="buyer-card border-dashed p-10 text-center"><h3 className="text-xl font-extrabold">{error === "filters" ? "Check your filters" : "Marketplace is unavailable"}</h3><p className="buyer-muted mt-2 text-sm">{error === "filters" ? "Use a valid category, price range and recent-first ordering." : "We could not load live listings. Please try again."}</p><button type="button" onClick={() => router.refresh()} className="buyer-button mt-5">Retry</button>{error === "filters" && <Link href="/marketplace" className="buyer-button buyer-ghost ml-2">Clear filters</Link>}</div>
        : page && count ? <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">{page.listings.map(listing => <article key={listing.id} data-listing-id={listing.id} className="buyer-card group overflow-hidden transition hover:-translate-y-0.5 hover:shadow-lg">
          <Link href={listingHref(listing.id, query)} aria-label={`View ${listing.title}`} className="block overflow-hidden"><Image unoptimized src={listing.photos[0].url} alt={listing.title} width={listing.photos[0].width ?? 800} height={listing.photos[0].height ?? 600} className="aspect-[4/3] w-full object-cover" /></Link>
          <div className="grid gap-3 p-4"><div className="flex flex-wrap items-center justify-between gap-2"><span className={`rounded-full px-2.5 py-1 text-xs font-bold ${listing.condition === "faulty" ? "bg-orange-50 text-orange-800" : "bg-emerald-50 text-emerald-800"}`}>{conditions[listing.condition]}</span><time dateTime={listing.published_at} className="buyer-muted text-xs font-semibold">{new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(listing.published_at))}</time></div>
            <div><h3 className="truncate text-base font-extrabold">{listing.title}</h3><p className="mt-1 text-xl font-extrabold tracking-tight text-[#064829]">{formatMoney(listing.price)}<span className="buyer-muted ml-1 text-xs font-medium">{priceBasis(listing)}</span></p></div>
            <p className="buyer-muted flex items-center gap-1 text-xs font-semibold"><BuyerIcon name="pin" className="size-4" />{listing.location_summary}</p><p className="buyer-muted text-xs font-semibold">{listing.vendor.business_name} · Verified vendor</p><p className="buyer-muted text-xs font-semibold">{formatQuantity(listing.available_quantity)} available</p>
            <Link href={listingHref(listing.id, query)} className="buyer-button w-full">View item</Link></div></article>)}</div>
        : page ? <div className="buyer-card border-dashed p-10 text-center"><BuyerIcon name="search" className="buyer-muted mx-auto size-10" /><h3 className="mt-4 text-xl font-extrabold">{page.next_cursor ? "No listings on this page" : "No matching listings"}</h3><p className="buyer-muted mt-2 text-sm">{page.next_cursor ? "More listings may appear on the next page." : "Try another word or clear your filters."}</p><Link href="/marketplace" className="buyer-button mt-5">Clear filters</Link></div> : null}
        {page?.next_cursor && <nav aria-label="Marketplace pages" className="mt-6 flex justify-center"><Link className="buyer-button" href={catalogueHref({ ...query, cursor: page.next_cursor })}>Next page</Link></nav>}
      </section>
    </div>
  </>;
}
