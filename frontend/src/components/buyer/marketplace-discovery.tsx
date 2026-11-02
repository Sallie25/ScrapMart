"use client";
import { useState, type ReactNode } from "react";
import Link from "next/link";
import { buyerListings } from "@/lib/data/buyer-fixtures";
import { BuyerListingCard } from "./buyer-listing-card";
import { BuyerIcon } from "./buyer-icon";
const allListings = buyerListings;
const categories = Array.from(
  new Set(allListings.map((l) => l.category)),
).sort();
function FilterSelect({
  id,
  label,
  value,
  onChange,
  children,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
}) {
  return (
    <label htmlFor={id} className="grid gap-2 text-sm font-bold">
      {label}
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        {children}
      </select>
    </label>
  );
}
export function MarketplaceDiscovery({
  initialCategory = "All",
  initialQuery = "",
}: {
  initialCategory?: string;
  initialQuery?: string;
}) {
  const [searchQuery, setSearchQuery] = useState(initialQuery);
  const [verifiedOnly, setVerifiedOnly] = useState(false);
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
        selectedCategory === "All" || listing.category === selectedCategory;

      const matchesLocation =
        selectedLocation === "All" || listing.location === selectedLocation;

      const matchesCondition =
        selectedCondition === "All" || listing.condition === selectedCondition;

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
        matchesMaxPrice &&
        (!verifiedOnly || listing.verifiedVendor)
      );
    })
    .sort((a, b) => {
      if (sortOption === "price-low") {
        return a.price - b.price;
      }

      if (sortOption === "price-high") {
        return b.price - a.price;
      }

      return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
    });

  function clearFilters() {
    setSearchQuery("");
    setSelectedCategory("All");
    setSelectedLocation("All");
    setSelectedCondition("All");
    setMinPrice("");
    setMaxPrice("");
    setSortOption("newest");
    setVerifiedOnly(false);
  }

  return (
    <>
      <Link
        href="/buyer/dashboard"
        className="buyer-muted mb-5 inline-flex min-h-11 items-center gap-2 text-sm font-bold"
      >
        <BuyerIcon name="arrow" />
        Back to home
      </Link>
      <div className="flex items-end justify-between gap-4">
        <div>
          <p className="buyer-eyebrow">Marketplace</p>
          <h1 className="buyer-title">Find scrap</h1>
        </div>
        <p className="buyer-muted text-sm font-bold">
          {filteredListings.length} sample items
        </p>
      </div>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          document.getElementById("marketplace-results")?.focus();
        }}
        className="mt-5 flex flex-wrap gap-2 rounded-2xl border border-[#dfe6e1] bg-white p-2 shadow-sm"
      >
        <label htmlFor="listing-search" className="sr-only">
          Search scrap materials
        </label>
        <span className="buyer-muted grid size-11 place-items-center">
          <BuyerIcon name="search" />
        </span>
        <input
          id="listing-search"
          type="search"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Try engine or copper"
          className="min-w-0 flex-1 font-semibold"
        />
        <button type="submit" className="buyer-button max-sm:w-full">
          Search
        </button>
      </form>
      <div className="mt-6 grid gap-6 lg:grid-cols-[16rem_1fr]">
        <aside className="buyer-card h-fit p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-extrabold">Filters</h2>
            <BuyerIcon name="filter" />
          </div>
          <div className="mt-5 grid gap-5">
            <FilterSelect
              id="listing-category"
              label="Category"
              value={selectedCategory}
              onChange={setSelectedCategory}
            >
              <option value="All">All categories</option>
              {categories.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </FilterSelect>
            <FilterSelect
              id="listing-location"
              label="Location"
              value={selectedLocation}
              onChange={setSelectedLocation}
            >
              <option value="All">All locations</option>
              {locations.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </FilterSelect>
            <FilterSelect
              id="listing-condition"
              label="Condition"
              value={selectedCondition}
              onChange={setSelectedCondition}
            >
              <option value="All">All conditions</option>
              {conditions.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </FilterSelect>
            <fieldset>
              <legend className="mb-2 text-sm font-bold">
                Price range (₦)
              </legend>
              <div className="grid gap-3">
                <label
                  className="grid gap-1 text-xs font-semibold"
                  htmlFor="minimum-price"
                >
                  Minimum price
                  <input
                    id="minimum-price"
                    type="number"
                    min="0"
                    step="any"
                    value={minPrice}
                    onChange={(e) => setMinPrice(e.target.value)}
                    placeholder="e.g. 300"
                  />
                </label>
                <label
                  className="grid gap-1 text-xs font-semibold"
                  htmlFor="maximum-price"
                >
                  Maximum price
                  <input
                    id="maximum-price"
                    type="number"
                    min="0"
                    step="any"
                    value={maxPrice}
                    onChange={(e) => setMaxPrice(e.target.value)}
                    placeholder="e.g. 5000"
                  />
                </label>
              </div>
              {minPrice !== "" &&
                maxPrice !== "" &&
                Number(minPrice) > Number(maxPrice) && (
                  <p role="alert" className="mt-2 text-sm text-red-700">
                    Minimum price cannot be greater than maximum price.
                  </p>
                )}
            </fieldset>
            <label
              className="flex items-center justify-between gap-3 text-sm font-bold"
              htmlFor="verified-fixtures"
            >
              Sample verification flag only
              <input
                id="verified-fixtures"
                type="checkbox"
                role="switch"
                checked={verifiedOnly}
                onChange={(e) => setVerifiedOnly(e.target.checked)}
                className="size-5"
              />
            </label>
            <p className="buyer-muted text-xs leading-relaxed">
              Fixture flags are not real vendor verification. Category labels
              and price sorting here apply to presentation data.
            </p>
            <button
              type="button"
              onClick={clearFilters}
              className="buyer-button buyer-ghost"
            >
              Clear filters
            </button>
          </div>
        </aside>
        <section className="min-w-0">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2
              id="marketplace-results"
              tabIndex={-1}
              className="buyer-muted text-sm font-bold"
              aria-live="polite"
            >
              Showing {filteredListings.length} sample listings
            </h2>
            <label
              htmlFor="listing-sort"
              className="flex items-center gap-2 text-sm font-bold"
            >
              Sort by
              <select
                id="listing-sort"
                value={sortOption}
                onChange={(e) => setSortOption(e.target.value)}
              >
                <option value="newest">Newest first</option>
                <option value="price-low">Price: low to high</option>
                <option value="price-high">Price: high to low</option>
              </select>
            </label>
          </div>
          {filteredListings.length ? (
            <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
              {filteredListings.map((listing) => (
                <BuyerListingCard key={listing.id} listing={listing} />
              ))}
            </div>
          ) : (
            <div className="buyer-card border-dashed p-10 text-center">
              <BuyerIcon
                name="search"
                className="buyer-muted mx-auto size-10"
              />
              <h3 className="mt-4 text-xl font-extrabold">
                No matching listings
              </h3>
              <p className="buyer-muted mt-2 text-sm">
                Try another word or clear your filters.
              </p>
              <button
                type="button"
                onClick={clearFilters}
                className="buyer-button mt-5"
              >
                Clear filters
              </button>
            </div>
          )}
        </section>
      </div>
    </>
  );
}
