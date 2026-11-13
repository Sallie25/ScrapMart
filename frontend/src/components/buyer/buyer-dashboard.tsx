import Link from "next/link";
import type { MarketplaceView } from "@/lib/server/marketplace/page-data";
import { BuyerIcon } from "./buyer-icon";
import { LiveBuyerListingCard, LiveCategoryGrid } from "./live-overview";
import { BuyerOrderHistory } from "./buyer-order-history";
import { AccountMessages } from "@/components/account/account-messages";
export function BuyerDashboard({ view, marketplace }: { view?: string; marketplace: MarketplaceView }) {
  if (view === "orders")
    return <BuyerOrderHistory />;
  if (view === "messages") return <AccountMessages role="buyer" />;
  const unavailable: Record<string, string> = {
    profile: "My Profile",
    settings: "Settings",
    notifications: "Notifications",
  };
  if (view && unavailable[view])
    return (
      <section className="buyer-card mx-auto max-w-3xl p-7 sm:p-10">
        <p className="buyer-eyebrow">Buyer workspace</p>
        <h1 className="buyer-title mt-2">{unavailable[view]}</h1>
        <p className="buyer-muted mt-4 leading-relaxed">
          This view has no connected account data yet; no orders, messages,
          notifications or account changes have been created.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link href="/marketplace" className="buyer-button">
            Browse marketplace
          </Link>
          <Link href="/buyer/dashboard" className="buyer-button buyer-ghost">
            Back to overview
          </Link>
        </div>
      </section>
    );
  return (
    <>
      <section className="buyer-dark relative overflow-hidden rounded-3xl px-6 py-8 text-white lg:px-9 lg:py-9">
        <div className="absolute right-0 top-0 h-full w-2/5 bg-[radial-gradient(circle_at_center,rgba(74,222,128,.18),transparent_70%)]" />
        <div className="relative max-w-3xl">
          <p className="text-sm font-bold text-[#74d99b]">
            Buyer workspace · Signed in
          </p>
          <h1 className="mt-2 text-3xl font-extrabold tracking-tight md:text-4xl">
            Welcome to your buyer dashboard
          </h1>
          <p className="mt-2 text-sm text-slate-300">
            Explore live materials from approved vendors. Orders and messages
            remain available only when their account services are connected.
          </p>
          <form
            action="/marketplace"
            className="mt-6 flex flex-wrap gap-2 rounded-2xl bg-white p-2 shadow-xl"
          >
            <label htmlFor="buyer-dashboard-search" className="sr-only">
              Search marketplace
            </label>
            <span className="buyer-muted grid size-12 place-items-center">
              <BuyerIcon name="search" />
            </span>
            <input
              id="buyer-dashboard-search"
              name="q"
              type="search"
              className="min-w-0 flex-1 px-2 font-semibold"
              placeholder="Search engine, copper, battery..."
            />
            <button type="submit" className="buyer-button max-sm:w-full">
              Search marketplace
            </button>
          </form>
        </div>
      </section>
      <section
        aria-label="Buyer overview"
        className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4"
      >
        {[
          ["Active orders", "—", "orders", "/buyer/dashboard?view=orders"],
          ["Unread messages", "—", "message", "/buyer/dashboard?view=messages"],
          ["Verified vendors", "—", "check", "/marketplace"],
          ["Live listings", marketplace.page ? String(marketplace.page.listings.length) : "—", "pin", "/marketplace"],
        ].map(([label, value, icon, href]) => (
          <Link
            key={label}
            href={href}
            className="buyer-card flex items-center gap-4 p-5 transition hover:-translate-y-0.5 hover:border-[#08783e]/30"
          >
            <span className="buyer-soft buyer-green grid size-11 shrink-0 place-items-center rounded-xl">
              <BuyerIcon name={icon} />
            </span>
            <span>
              <strong className="buyer-display block text-2xl">{value}</strong>
              <span className="buyer-muted text-sm font-semibold">{label}</span>
              <span className="buyer-muted mt-1 block text-[10px]">
                {label === "Live listings" ? "Current marketplace page" : "Not connected"}
              </span>
            </span>
            <BuyerIcon name="chevron" className="buyer-muted ml-auto size-4" />
          </Link>
        ))}
      </section>
      <section className="mt-9">
        <div className="flex items-end justify-between gap-3">
          <div>
            <p className="buyer-eyebrow">Browse quickly</p>
            <h2 className="buyer-title">Categories</h2>
          </div>
          <Link href="/categories" className="buyer-green text-sm font-bold">
            View all
          </Link>
        </div>
        {marketplace.error ? <p role="alert" className="buyer-muted mt-5">Live categories are unavailable.</p> : <LiveCategoryGrid categories={marketplace.categories} />}
      </section>
      <section className="mt-10">
        <div className="flex items-end justify-between gap-3">
          <div>
            <p className="buyer-eyebrow">Live marketplace</p>
            <h2 className="buyer-title">Recent scrap</h2>
          </div>
          <Link href="/marketplace" className="buyer-green text-sm font-bold">
            See more
          </Link>
        </div>
        <div className="mt-5 grid gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {marketplace.page?.listings.slice(0, 4).map(listing => <LiveBuyerListingCard key={listing.id} listing={listing} />)}
        </div>
        {marketplace.error && <p role="alert" className="buyer-muted mt-4">Live listings are unavailable. Please try again later.</p>}
        {!marketplace.error && marketplace.page?.listings.length === 0 && <p className="buyer-muted mt-4">No listings are published yet.</p>}
      </section>
      <aside className="mt-10 flex flex-col gap-4 rounded-3xl border border-amber-200 bg-amber-50 p-5 md:flex-row md:items-center md:justify-between">
        <div className="flex gap-3">
          <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-amber-100 text-amber-800">
            <BuyerIcon name="check" />
          </span>
          <div>
            <h2 className="text-lg font-extrabold">
              Your money stays with you
            </h2>
            <p className="mt-1 text-sm text-amber-900">
              Pay on Delivery is the intended policy. Never send money before
              receiving your item.
            </p>
          </div>
        </div>
        <Link
          href="/how-it-works"
          className="buyer-button buyer-ghost shrink-0"
        >
          Safety tips
        </Link>
      </aside>
    </>
  );
}
