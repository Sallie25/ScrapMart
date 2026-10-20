
"use client";

import { Suspense, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { SiteHeader } from "@/components/layout/site-header";
import { ListingCard } from "@/components/marketplace/listing-card";
import { Container } from "@/components/ui/container";
import { demoListings } from "@/lib/data/listings";

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
          <main className="min-h-screen bg-[#f4f7f5] py-6">
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

      <main className="min-h-screen bg-[#f4f7f5] py-6">
        <Container size="wide">
          <section aria-labelledby="marketplace-title" className="rounded-3xl bg-[#064d31] px-5 py-6 text-white sm:px-10 sm:py-8">
            <p className="text-sm font-semibold text-[#70dfa8]">Welcome to ScrapMart</p>
            <h1 id="marketplace-title" className="mt-2 text-3xl font-bold tracking-tight sm:text-5xl">What scrap do you need today?</h1>
            <form className="mt-5 max-w-3xl" onSubmit={(event) => {
              event.preventDefault();
              document.getElementById("marketplace-results")?.focus();
            }}>
              <label htmlFor="listing-search" className="sr-only">Search scrap materials</label>
              <div className="flex flex-col gap-2 rounded-2xl bg-white p-2 sm:flex-row">
                <input id="listing-search" type="search" value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  placeholder="Search copper, plastics, aluminium..."
                  className="min-h-12 min-w-0 flex-1 rounded-xl px-4 text-[#15221b] outline-none placeholder:text-[#63736c] focus-visible:ring-2 focus-visible:ring-[#087b40]" />
                <button type="submit" className="min-h-12 rounded-xl bg-[#087b40] px-6 py-3 text-sm font-semibold text-white hover:bg-[#066333] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#087b40]">Search</button>
              </div>
              <p className="mt-3 text-xs leading-5 text-[#b6dfcc]">Try searching: copper · plastics · aluminium</p>
            </form>
          </section>

          <section aria-labelledby="categories-title" className="mt-6">
            <p className="text-xs font-bold uppercase tracking-widest text-[#087b40]">Browse quickly</p>
            <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
              <h2 id="categories-title" className="text-3xl font-bold tracking-tight text-[#15221b]">Categories</h2>
              <Link href="/categories" className="inline-flex min-h-11 items-center rounded-lg px-2 text-sm font-medium text-[#087b40] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#087b40]">View all</Link>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-3 sm:flex sm:flex-wrap">
              {categories.map((category) => {
                const categoryImage = ({ Metals: "/images/category-metals.jpg", Plastics: "/images/category-plastics.jpg", Electronics: "/images/category-electronics.jpg" } as Record<string, string>)[category];
                return (
                  <Link key={category} href={`/marketplace?category=${encodeURIComponent(category)}`}
                    className={`flex min-w-0 flex-col items-center gap-2 rounded-2xl border bg-white p-2 pb-3 text-xs font-bold text-[#15221b] transition-shadow hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#087b40] sm:w-32 ${selectedCategory === category ? "border-[#087b40] ring-1 ring-[#087b40]" : "border-[#dce4df]"}`}>
                    {categoryImage ? <Image src={categoryImage} alt={`${category} materials`} width={112} height={104} className="h-24 w-full rounded-xl object-cover" /> : <span className="flex h-24 w-full items-center justify-center rounded-xl bg-[#edf2ef] text-4xl" aria-hidden="true">📦</span>}
                    {category}
                  </Link>
                );
              })}
            </div>
          </section>

          <section aria-labelledby="browse-controls-title" className="mt-6 rounded-2xl border border-[#dce4df] bg-white p-4">
            <h2 id="browse-controls-title" className="mb-3 text-lg font-bold text-[#15221b]">Refine your search</h2>
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

          </section>

          <section aria-labelledby="marketplace-results" className="mt-10">
            <p className="mb-3 text-xs font-bold uppercase tracking-widest text-[#087b40]">Explore materials</p>
            <div className="mb-5 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
              <div>
                <h2 id="marketplace-results" tabIndex={-1} className="scroll-mt-6 rounded text-3xl font-bold tracking-tight text-[#15221b] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#087b40]">
                  Browse scrap
                </h2>

                <p className="text-sm text-muted" aria-live="polite">
                  Demo marketplace · {filteredListings.length}{" "}
                  {filteredListings.length === 1 ? "listing" : "listings"}
                </p>
              </div>

              <div className="sm:w-64">
                <label
                  htmlFor="listing-sort"
                  className="mb-2 block text-sm font-medium text-text"
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
              <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
                {filteredListings.map((listing) => (
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

          <aside aria-labelledby="payment-safety-title" className="mt-10 flex flex-col gap-5 rounded-3xl border border-amber-300 bg-amber-50 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
            <div className="flex items-start gap-3">
              <span aria-hidden="true" className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-amber-100 text-amber-800">✓</span>
              <div>
                <h2 id="payment-safety-title" className="text-lg font-bold text-[#15221b]">Your money stays with you</h2>
                <p className="mt-1 text-sm leading-6 text-amber-800">ScrapMart uses Pay on Delivery. Never pay before receiving your item. No advance payment required by ScrapMart.</p>
              </div>
            </div>
            <Link href="/how-it-works" className="inline-flex min-h-12 shrink-0 items-center justify-center rounded-xl border border-[#dce4df] bg-white px-5 py-3 text-sm font-medium text-[#15221b] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#087b40]">Safety tips</Link>
          </aside>
        </Container>
      </main>
    </>
  );
}
