
"use client";

import { Suspense, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { SiteHeader } from "@/components/layout/site-header";
import { ListingCard } from "@/components/marketplace/listing-card";
import { Container } from "@/components/ui/container";
import { demoListings } from "@/lib/data/listings";

// Presentation/discovery labels do not extend the canonical filter taxonomy.
// New category photographs: Pexels License (https://www.pexels.com/license/).
const discoveryCategories = [
  { label: "Clothes", image: "/images/category-clothes.jpg", placeholder: "♧" }, // https://www.pexels.com/photo/assorted-clothes-hanged-on-a-clothes-rack-6068952/
  { label: "Scrap Metal", image: "/images/category-metals.jpg", category: "Metals" },
  { label: "Aluminium", image: "/images/category-aluminium.jpg", placeholder: "Al" }, // https://www.pexels.com/photo/smashed-cans-in-close-up-shot-4593026/
  { label: "Copper", image: "/images/category-copper.jpg", placeholder: "Cu" }, // https://www.pexels.com/photo/close-up-photo-of-copper-wires-5279317/
  { label: "Iron", image: "/images/category-iron.jpg", placeholder: "Fe" }, // https://www.pexels.com/photo/close-up-of-stacked-rusty-iron-17367619/
  { label: "Electronics", image: "/images/category-electronics.jpg", category: "Electronics" },
  { label: "Car Parts", image: "/images/category-car-parts.jpg", placeholder: "⚙" }, // https://www.pexels.com/photo/battery-and-distributor-of-modern-car-4517069/
  { label: "Machinery", image: "/images/category-machinery.jpg", placeholder: "⚒" }, // https://www.pexels.com/photo/close-up-shot-of-metal-gears-4843915/
  { label: "Batteries", image: "/images/category-batteries.jpg", placeholder: "▥" }, // https://www.pexels.com/photo/close-up-photo-of-car-s-battery-4374843/
  { label: "Plastics", image: "/images/category-plastics.jpg", category: "Plastics" },
  { label: "Other", image: "/images/category-other.jpg", placeholder: "···" }, // https://www.pexels.com/photo/abstract-still-life-of-industrial-scrap-metal-30789632/
];

const allListings = demoListings;
const categories = Array.from(
  new Set(allListings.map((listing) => listing.category)),
).sort();

export default function MarketplacePage() {
  return (
    <Suspense
      fallback={
        <>
          <SiteHeader variant="marketplace" />
          <main className="min-h-screen bg-[#f4f7f5] pb-12 pt-6">
            <Container size="wide">
              <p role="status" className="text-muted">Loading marketplace...</p>
            </Container>
          </main>
        </>
      }
    >
      <MarketplaceFromQuery />
    </Suspense>
  );
}

function MarketplaceFromQuery() {
  const searchParams = useSearchParams();
  const rawCategory = searchParams.get("category");
  const initialCategory = categories.find(
    (category) => category.toLowerCase() === (rawCategory ?? "").trim().toLowerCase(),
  ) ?? "All";

  return (
    <MarketplaceContent
      key={rawCategory ?? ""}
      initialCategory={initialCategory}
    />
  );
}

function MarketplaceContent({ initialCategory }: { initialCategory: string }) {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState(initialCategory);
  const [selectedLocation, setSelectedLocation] = useState("All");
  const [selectedCondition, setSelectedCondition] = useState("All");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [sortOption, setSortOption] = useState("newest");

  const locations = Array.from(
    new Set(allListings.map((listing) => listing.location)),
  ).sort();

  const conditions = Array.from(
    new Set(allListings.map((listing) => listing.condition)),
  ).sort();

  const filteredListings = allListings
    .filter((listing) => {
      const query = searchQuery.trim().toLowerCase();

      const matchesSearch =
        !query ||
        [
          listing.title,
          listing.description,
          listing.category,
          listing.location,
          listing.vendorName,
        ].some((value) => value.toLowerCase().includes(query));

      const matchesCategory =
        selectedCategory === "All" ||
        listing.category === selectedCategory;

      const matchesLocation =
        selectedLocation === "All" ||
        listing.location === selectedLocation;

      const matchesCondition =
        selectedCondition === "All" ||
        listing.condition === selectedCondition;

      const matchesMinPrice =
        minPrice === "" || listing.price >= Number(minPrice);

      const matchesMaxPrice =
        maxPrice === "" || listing.price <= Number(maxPrice);

      return (
        matchesSearch &&
        matchesCategory &&
        matchesLocation &&
        matchesCondition &&
        matchesMinPrice &&
        matchesMaxPrice
      );
    })
    .sort((a, b) => {
      if (sortOption === "price-low") {
        return a.price - b.price;
      }

      if (sortOption === "price-high") {
        return b.price - a.price;
      }

      return (
        new Date(b.createdAt).getTime() -
        new Date(a.createdAt).getTime()
      );
    });

  function clearFilters() {
    setSearchQuery("");
    setSelectedCategory("All");
    setSelectedLocation("All");
    setSelectedCondition("All");
    setMinPrice("");
    setMaxPrice("");
    setSortOption("newest");
  }

  return (
    <>
      <SiteHeader variant="marketplace" />

      <main className="min-h-screen bg-[#f4f7f5] pb-12 pt-6">
        <Container size="wide">
          <section aria-labelledby="marketplace-title" className="rounded-[24px] bg-[radial-gradient(ellipse_at_75%_50%,#0d5938_0%,#064d31_70%)] px-5 py-8 text-white sm:px-10 sm:py-12">
            <p className="text-sm font-semibold text-[#70dfa8]">Welcome to ScrapMart</p>
            <h1 id="marketplace-title" className="mt-2 text-3xl font-bold leading-[1.15] tracking-[-0.035em] sm:text-5xl">What scrap do you need today?</h1>
            <form className="mt-6 max-w-3xl" onSubmit={(event) => {
              event.preventDefault();
              document.getElementById("marketplace-results")?.focus();
            }}>
              <label htmlFor="listing-search" className="sr-only">Search scrap materials</label>
              <div className="flex flex-col gap-2 rounded-2xl bg-white p-2 shadow-sm sm:flex-row sm:items-center">
                <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="ml-3 hidden h-5 w-5 shrink-0 text-[#63736c] sm:block"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4.5 4.5" /></svg>
                <input id="listing-search" type="search" value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  placeholder="Search engine, copper, battery..."
                  className="min-h-12 min-w-0 flex-1 rounded-xl px-4 text-[#15221b] outline-none placeholder:text-[#63736c] focus-visible:ring-2 focus-visible:ring-[#087b40]" />
                <button type="submit" className="min-h-12 rounded-xl bg-[#087b40] px-6 py-3 text-sm font-semibold text-white hover:bg-[#066333] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#087b40]">Search</button>
              </div>
              <p className="mt-3 text-xs leading-5 text-[#b6dfcc]">Popular: Toyota engine · copper wire · batteries · generator</p>
            </form>
          </section>

          <section aria-labelledby="categories-title" className="mt-9">
            <p className="text-xs font-bold uppercase tracking-widest text-[#087b40]">Browse quickly</p>
            <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
              <h2 id="categories-title" className="text-3xl font-bold tracking-[-0.035em] text-[#15221b] sm:text-4xl">Categories</h2>
              <Link href="/categories" className="inline-flex min-h-11 items-center rounded-lg px-2 text-sm font-medium text-[#087b40] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#087b40]">View all</Link>
            </div>
            <div className="mt-5 grid auto-cols-[122px] grid-flow-col gap-3 overflow-x-auto pb-2 lg:auto-cols-auto lg:grid-flow-row lg:grid-cols-11 lg:overflow-visible lg:pb-0">
              {discoveryCategories.map((item) => {
                const tileContent = (
                  <>
                    {item.image ? (
                      <Image src={item.image} alt={`${item.label} materials`} width={104} height={104} sizes="(min-width: 1024px) 7vw, 104px" className="aspect-square w-full rounded-xl object-cover" />
                    ) : (
                      <span aria-label="Image unavailable" className="flex aspect-square w-full flex-col items-center justify-center gap-1 rounded-xl bg-[linear-gradient(145deg,#edf2ef,#dce8df)] text-[#63736c]">
                        <span aria-hidden="true" className="text-3xl font-medium">{item.placeholder}</span>
                        <span className="text-[9px] font-normal">No image</span>
                      </span>
                    )}
                    <span className="whitespace-nowrap">{item.label}</span>
                  </>
                );
                const tileClass = "flex min-w-0 flex-col items-center gap-2 rounded-2xl border bg-white p-2 pb-3 text-[11px] font-bold text-[#15221b]";
                return item.category ? (
                  <Link key={item.label} href={`/marketplace?category=${encodeURIComponent(item.category)}`}
                    aria-label={item.label === "Scrap Metal" ? "Scrap Metal: browse Metals" : `Browse ${item.label}`}
                    className={`${tileClass} transition-shadow hover:border-[#087b40] hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#087b40] ${selectedCategory === item.category ? "border-[#087b40] ring-1 ring-[#087b40]" : "border-[#dce4df]"}`}>
                    {tileContent}
                  </Link>
                ) : (
                  <div key={item.label} title="Presentation category only; no category filter available" className={`${tileClass} border-[#dce4df]`}>
                    {tileContent}
                  </div>
                );
              })}
            </div>
            <p className="mt-2 text-[11px] text-[#63736c]">Demo discovery categories · Electronics, Metals, Paper and Plastics are available in filters. Other tiles are presentation only.</p>
          </section>

          <details className="mt-4 border-b border-[#dce4df] px-1 open:rounded-2xl open:border open:bg-white open:px-5 open:pb-5">
            <summary className="cursor-pointer rounded-lg py-3 text-sm font-semibold text-[#15221b] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#087b40]">
              Refine your search
              <span className="ml-2 font-normal text-[#63736c]">
                · Category, location, condition &amp; price
                {(selectedCategory !== "All" || selectedLocation !== "All" || selectedCondition !== "All" || minPrice !== "" || maxPrice !== "") && " · Filters active"}
              </span>
            </summary>
            <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <label
                  htmlFor="listing-category"
                  className="mb-1 block text-sm font-medium text-text"
                >
                  Category
                </label>

                <select
                  id="listing-category"
                  value={selectedCategory}
                  onChange={(event) => setSelectedCategory(event.target.value)}
                  className="w-full rounded-lg border border-border bg-white px-4 py-3 text-text outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                >
                  <option value="All">All categories</option>
                  {categories.map((category) => (
                    <option key={category} value={category}>
                      {category}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label
                  htmlFor="listing-location"
                  className="mb-1 block text-sm font-medium text-text"
                >
                  Location
                </label>

                <select
                  id="listing-location"
                  value={selectedLocation}
                  onChange={(event) => setSelectedLocation(event.target.value)}
                  className="w-full rounded-lg border border-border bg-white px-4 py-3 text-text outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                >
                  <option value="All">All locations</option>
                  {locations.map((location) => (
                    <option key={location} value={location}>
                      {location}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label
                  htmlFor="listing-condition"
                  className="mb-1 block text-sm font-medium text-text"
                >
                  Condition
                </label>

                <select
                  id="listing-condition"
                  value={selectedCondition}
                  onChange={(event) => setSelectedCondition(event.target.value)}
                  className="w-full rounded-lg border border-border bg-white px-4 py-3 text-text outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                >
                  <option value="All">All conditions</option>
                  {conditions.map((condition) => (
                    <option key={condition} value={condition}>
                      {condition}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="rounded-xl border border-border bg-white p-3">
              <h3 className="mb-2 font-semibold text-text">
                Price range (₦)
              </h3>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <label
                    htmlFor="minimum-price"
                    className="mb-1 block text-sm text-text"
                  >
                    Minimum price
                  </label>

                  <input
                    id="minimum-price"
                    type="number"
                    min="0"
                    step="any"
                    value={minPrice}
                    onChange={(event) => setMinPrice(event.target.value)}
                    placeholder="e.g. 300"
                    className="w-full rounded-lg border border-border bg-white px-4 py-3 text-text outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                  />
                </div>

                <div>
                  <label
                    htmlFor="maximum-price"
                    className="mb-1 block text-sm text-text"
                  >
                    Maximum price
                  </label>

                  <input
                    id="maximum-price"
                    type="number"
                    min="0"
                    step="any"
                    value={maxPrice}
                    onChange={(event) => setMaxPrice(event.target.value)}
                    placeholder="e.g. 5000"
                    className="w-full rounded-lg border border-border bg-white px-4 py-3 text-text outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                  />
                </div>
              </div>

              {minPrice !== "" &&
                maxPrice !== "" &&
                Number(minPrice) > Number(maxPrice) && (
                  <p className="mt-3 text-sm text-red-600" role="alert">
                    Minimum price cannot be greater than maximum price.
                  </p>
                )}
            </div>

            <button type="button" onClick={clearFilters} className="mt-3 min-h-11 rounded-lg px-3 text-sm font-semibold text-[#087b40] hover:bg-[#edf5ef] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#087b40]">Clear filters</button>
          </details>

          <section aria-labelledby="marketplace-results" className="mt-6">
            <p className="mb-2 text-xs font-bold uppercase tracking-widest text-[#087b40]">Explore materials</p>
            <div className="mb-5 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
              <div>
                <h2 id="marketplace-results" tabIndex={-1} className="scroll-mt-6 rounded text-3xl font-bold tracking-[-0.035em] text-[#15221b] sm:text-4xl focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#087b40]">
                  Browse scrap
                </h2>

                <p className="mt-2 text-sm text-[#63736c]" aria-live="polite">
                  Demo marketplace · {filteredListings.length}{" "}
                  {filteredListings.length === 1 ? "listing" : "listings"}
                </p>
              </div>

              <div className="flex items-center gap-3">
                <label
                  htmlFor="listing-sort"
                  className="shrink-0 text-sm font-medium text-[#63736c]"
                >
                  Sort by
                </label>

                <select
                  id="listing-sort"
                  value={sortOption}
                  onChange={(event) => setSortOption(event.target.value)}
                  className="w-full rounded-lg border border-border bg-white px-4 py-3 text-text outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                >
                  <option value="newest">Newest first</option>
                  <option value="price-low">Price: low to high</option>
                  <option value="price-high">Price: high to low</option>
                </select>
              </div>
            </div>

            {filteredListings.length > 0 ? (
              <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
                {filteredListings.slice(0, 4).map((listing) => (
                  <ListingCard key={listing.id} listing={listing} variant="marketplace" />
                ))}
              </div>
            ) : (
              <div className="rounded-xl border border-border bg-white px-6 py-12 text-center">
                <h3 className="text-lg font-semibold text-text">
                  No matching listings
                </h3>

                <p className="mt-2 text-sm text-muted">
                  Try changing your search or filters to see available
                  materials.
                </p>

                <button
                  type="button"
                  onClick={clearFilters}
                  className="mt-5 min-h-11 rounded-lg bg-primary px-4 py-2 font-medium text-white transition hover:opacity-90"
                >
                  Clear filters
                </button>
              </div>
            )}
          </section>

          <aside aria-labelledby="payment-safety-title" className="mt-10 flex flex-col gap-5 rounded-[24px] border border-amber-300 bg-[#fffbeb] p-5 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <span aria-hidden="true" className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-amber-100 text-amber-800">✓</span>
              <div>
                <h2 id="payment-safety-title" className="text-lg font-bold text-[#15221b]">Your money stays with you</h2>
                <p className="mt-1 text-sm leading-6 text-amber-800">ScrapMart uses Pay on Delivery. Never send money before receiving your item.</p>
              </div>
            </div>
            <Link href="/how-it-works" className="inline-flex min-h-12 shrink-0 items-center justify-center rounded-xl border border-[#dce4df] bg-white px-5 py-3 text-sm font-medium text-[#15221b] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#087b40]">Safety tips</Link>
          </aside>

          {filteredListings.length > 4 && (
            <section aria-labelledby="more-materials-title" className="mt-10">
              <h2 id="more-materials-title" className="mb-5 text-2xl font-bold tracking-tight text-[#15221b]">More materials</h2>
              <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
                {filteredListings.slice(4).map((listing) => (
                  <ListingCard key={listing.id} listing={listing} variant="marketplace" />
                ))}
              </div>
            </section>
          )}
        </Container>
      </main>
    </>
  );
}
