
"use client";

import { useState } from "react";
import { SiteHeader } from "@/components/layout/site-header";
import { ListingCard } from "@/components/marketplace/listing-card";
import { Container } from "@/components/ui/container";
import { PageHeader } from "@/components/ui/page-header";
import { demoListings } from "@/lib/data/listings";

export default function MarketplacePage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [selectedLocation, setSelectedLocation] = useState("All");
  const [selectedCondition, setSelectedCondition] = useState("All");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [sortOption, setSortOption] = useState("newest");

  const allListings = demoListings;

  const categories = Array.from(
    new Set(allListings.map((listing) => listing.category)),
  ).sort();

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
      <SiteHeader />

      <main className="min-h-screen bg-background py-10 sm:py-14">
        <Container>
          <PageHeader
            title="Discover scrap materials"
            description="Explore materials listed by vendors across Lagos."
          />

          <section className="mt-8">
            <div className="mb-6">
              <label
                htmlFor="listing-search"
                className="mb-2 block text-sm font-medium text-text"
              >
                Search scrap materials
              </label>

              <input
                id="listing-search"
                type="search"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="Try copper, Ikeja, plastics..."
                className="w-full rounded-lg border border-border bg-white px-4 py-3 text-text outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
              />
            </div>

            <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <label
                  htmlFor="listing-category"
                  className="mb-2 block text-sm font-medium text-text"
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
                  className="mb-2 block text-sm font-medium text-text"
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
                  className="mb-2 block text-sm font-medium text-text"
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

            <div className="mb-6 rounded-xl border border-border bg-white p-4">
              <h3 className="mb-4 font-semibold text-text">
                Price range (₦)
              </h3>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label
                    htmlFor="minimum-price"
                    className="mb-2 block text-sm text-text"
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
                    className="mb-2 block text-sm text-text"
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

            <div className="mb-5 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
              <div>
                <h2 className="text-lg font-semibold text-text">
                  Recently listed
                </h2>

                <p className="text-sm text-muted" aria-live="polite">
                  {filteredListings.length}{" "}
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
              <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
                {filteredListings.map((listing) => (
                  <ListingCard key={listing.id} listing={listing} />
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
                  className="mt-5 rounded-lg bg-primary px-4 py-2 font-medium text-white transition hover:opacity-90"
                >
                  Clear filters
                </button>
              </div>
            )}
          </section>
        </Container>
      </main>
    </>
  );
}
