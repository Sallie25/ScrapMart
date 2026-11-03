"use client";
import Link from "next/link";
import { ListingPhoto } from "@/components/marketplace/listing-photo";
import { useState } from "react";
import { designerListings } from "@/lib/data/buyer-fixtures";
import { VendorIcon } from "./vendor-icon";
import { VendorLocalListings } from "./vendor-local-listings";

type Status = "Active" | "Inactive" | "Sold" | "Draft";
const initial = designerListings.map((item) => ({
  ...item,
  status: "Active" as Status,
}));
const bulkSeed = [
  { ...initial[0], title: "Toyota Engine", price: 250000 },
  { ...initial[2], title: "Copper Wire", price: 90000 },
  { ...initial[4], title: "Mixed Metal Parts", price: 120000 },
];
const money = (value: number) =>
  new Intl.NumberFormat("en-NG", {
    style: "currency",
    currency: "NGN",
    maximumFractionDigits: 0,
  }).format(value);
const action = "vendor-button";
const ghost = "vendor-button vendor-ghost";
export function VendorWorkspace({ view }: { view?: string }) {
  const [items, setItems] = useState(initial);
  const [tab, setTab] = useState("All");
  const [notice, setNotice] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [bulk, setBulk] = useState(false);
  const [bulkItems, setBulkItems] = useState(bulkSeed);
  const update = (id: string, status: Status) => {
    setItems(
      items.map((item) => (item.id === id ? { ...item, status } : item)),
    );
    setNotice(
      `Sample status changed to ${status}. No marketplace listing changed.`,
    );
  };
  const back = (
    <Link
      href="/vendor/dashboard"
      className="vendor-muted mb-5 inline-flex min-h-11 items-center gap-2 text-sm font-bold"
    >
      <VendorIcon name="arrow" />
      Back to dashboard
    </Link>
  );
  if (view === "local")
    return (
      <>
        {back}
        <div className="vendor-legacy">
          <VendorLocalListings />
        </div>
      </>
    );
  if (view === "bulk")
    return (
      <div className="mx-auto max-w-5xl">
        {back}
        <p className="vendor-eyebrow">Bulk upload</p>
        <h1 className="vendor-title">Add multiple items</h1>
        <p className="vendor-muted mt-2 text-sm">
          Review sample illustrations and item names. Bulk publishing is
          unavailable.
        </p>
        {!bulk ? (
          <section className="vendor-card mt-7 grid min-h-72 place-items-center border-2 border-dashed p-8 text-center">
            <div>
              <VendorIcon name="upload" className="mx-auto size-8" />
              <h2 className="vendor-display mt-5 text-xl font-extrabold">
                Review sample items
              </h2>
              <p className="vendor-muted my-3 text-sm">
                Photo upload is available in the single-item form.
              </p>
              <button onClick={() => setBulk(true)} className={action}>
                Use 3 sample illustrations
              </button>
              <Link
                className="vendor-green mt-4 block text-sm font-bold"
                href="/vendor/listings/new"
              >
                Open single-item form
              </Link>
            </div>
          </section>
        ) : (
          <div className="mt-7">
            <div className="vendor-card overflow-x-auto">
              <table className="w-full min-w-[42rem] text-left">
                <thead className="bg-[#f5f7f5] text-xs uppercase">
                  <tr>
                    {["Image", "Item", "Category", "Price", "Actions"].map(
                      (label) => (
                        <th className="p-4" key={label}>
                          {label}
                        </th>
                      ),
                    )}
                  </tr>
                </thead>
                <tbody>
                  {bulkItems.map((item) => (
                    <tr key={item.id} className="border-t border-[#dfe6e1]">
                      <td className="p-3">
                        <ListingPhoto
                          listingId={item.id}
                          category={item.category}
                          title={item.title}
                          compact
                          className="size-14 rounded-lg shrink-0"
                        />
                      </td>
                      <td>
                        <input
                          aria-label={`Sample item name: ${item.title}`}
                          value={item.title}
                          onChange={(event) =>
                            setBulkItems(
                              bulkItems.map((row) =>
                                row.id === item.id
                                  ? { ...row, title: event.target.value }
                                  : row,
                              ),
                            )
                          }
                        />
                      </td>
                      <td className="p-3 text-sm">{item.category}</td>
                      <td className="p-3 font-bold">{money(item.price)}</td>
                      <td className="p-3">
                        <button
                          className="text-sm font-bold text-red-700"
                          onClick={() =>
                            setBulkItems(
                              bulkItems.filter((row) => row.id !== item.id),
                            )
                          }
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p role="status" className="vendor-muted mt-5 text-sm">
              {bulkItems.length} sample items in this review. Nothing has been
              uploaded or published.
            </p>
            <button
              className={`${ghost} mt-4`}
              onClick={() => {
                setBulk(false);
                setBulkItems(bulkSeed);
              }}
            >
              Reset sample review
            </button>
          </div>
        )}
      </div>
    );
  if (view === "listings")
    return (
      <>
        {back}
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="vendor-eyebrow">Your inventory</p>
            <h1 className="vendor-title">My Listings</h1>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link href="/vendor/dashboard?view=bulk" className={ghost}>
              Add multiple
            </Link>
            <Link href="/vendor/listings/new" className={action}>
              + Sell scrap
            </Link>
          </div>
        </div>
        <p className="vendor-muted mt-3 text-sm">
          Presentation fixtures below. Changes last only on this screen.{" "}
          <Link
            className="vendor-green font-bold underline"
            href="/vendor/listings?view=local"
          >
            Manage browser-saved demo listings
          </Link>
        </p>
        <div
          role="group"
          aria-label="Sample listing status"
          className="mt-6 flex flex-wrap gap-2"
        >
          {["All", "Active", "Sold", "Draft", "Inactive"].map((value) => (
            <button
              key={value}
              aria-pressed={tab === value}
              onClick={() => setTab(value)}
              className={`rounded-full border border-[#dfe6e1] px-4 py-2 text-sm font-bold ${tab === value ? "bg-[#14211a] text-white" : "bg-white"}`}
            >
              {value}
            </button>
          ))}
        </div>
        {notice && (
          <p role="status" className="vendor-soft mt-4 rounded-xl p-3 text-sm">
            {notice}
          </p>
        )}
        <div className="mt-5 grid gap-4">
          {items
            .filter((item) => tab === "All" || item.status === tab)
            .map((item) => (
              <article
                className="vendor-card flex flex-col gap-4 p-4 sm:flex-row sm:items-center"
                key={item.id}
              >
                <ListingPhoto
                  listingId={item.id}
                  category={item.category}
                  title={item.title}
                  compact
                  className="h-36 w-full rounded-xl sm:size-24 shrink-0"
                />
                <div className="min-w-0 flex-1">
                  <h2 className="vendor-display text-lg font-extrabold">
                    {item.title}
                  </h2>
                  <p className="vendor-green mt-1 font-bold">
                    {money(item.price)}
                  </p>
                  <p className="vendor-muted mt-1 text-xs">
                    Sample · {item.status} · No live availability
                  </p>
                  {editing === item.id && (
                    <form
                      className="mt-3 grid gap-2"
                      onSubmit={(event) => {
                        event.preventDefault();
                        const data = new FormData(event.currentTarget);
                        const title = String(data.get("title") ?? "").trim();
                        const price = Number(data.get("price"));
                        if (!title || !Number.isFinite(price) || price <= 0) {
                          setNotice("Enter an item name and a positive price.");
                          return;
                        }
                        setItems(
                          items.map((row) =>
                            row.id === item.id ? { ...row, title, price } : row,
                          ),
                        );
                        setEditing(null);
                        setNotice("Sample edited on this screen only.");
                      }}
                    >
                      <label className="text-sm font-bold">
                        Item name
                        <input
                          name="title"
                          defaultValue={item.title}
                          required
                          maxLength={200}
                        />
                      </label>
                      <label className="text-sm font-bold">
                        Price (₦)
                        <input
                          name="price"
                          type="number"
                          min="0.01"
                          step="0.01"
                          required
                          defaultValue={item.price}
                        />
                      </label>
                      <div className="flex gap-2">
                        <button className={action}>Save sample edit</button>
                        <button
                          type="button"
                          className={ghost}
                          onClick={() => setEditing(null)}
                        >
                          Cancel
                        </button>
                      </div>
                    </form>
                  )}
                </div>
                <div className="flex flex-wrap gap-2 sm:max-w-60">
                  <button className={ghost} onClick={() => setEditing(item.id)}>
                    Edit sample
                  </button>
                  {item.status !== "Sold" && (
                    <>
                      <button
                        className={ghost}
                        onClick={() =>
                          update(
                            item.id,
                            item.status === "Active" ? "Inactive" : "Active",
                          )
                        }
                      >
                        {item.status === "Active"
                          ? "Pause sample"
                          : "Activate sample"}
                      </button>
                      <button
                        className={ghost}
                        onClick={() => update(item.id, "Sold")}
                      >
                        Mark sample sold
                      </button>
                    </>
                  )}
                  <button
                    className={`${ghost} text-red-700`}
                    onClick={() => {
                      if (
                        window.confirm(
                          "Remove this fixture from the current screen only?",
                        )
                      ) {
                        setItems(items.filter((row) => row.id !== item.id));
                        setNotice("Sample removed from this screen only.");
                      }
                    }}
                  >
                    Remove sample
                  </button>
                </div>
              </article>
            ))}
        </div>
        {!items.some((item) => tab === "All" || item.status === tab) && (
          <p className="vendor-card mt-5 p-8 text-center">
            No sample listings in this status.
          </p>
        )}
      </>
    );
  if (view) {
    const titles: Record<string, string> = {
      orders: "Customer Orders",
      messages: "Messages",
      profile: "Vendor Profile & Verification",
      settings: "Store Settings",
      location: "My Shop Location",
      notifications: "Notifications",
    };
    return (
      <div className="mx-auto max-w-3xl">
        {back}
        <section className="vendor-card p-7">
          <p className="vendor-eyebrow">Vendor workspace</p>
          <h1 className="vendor-title">
            {titles[view] ?? "Service unavailable"}
          </h1>
          <p className="vendor-muted mt-4 leading-relaxed">
            This service is not connected in this presentation. No authenticated
            Vendor identity or verification state has been loaded. No orders,
            transactions or messages are shown as live.
          </p>
          <p className="vendor-soft mt-5 rounded-xl p-4 text-sm">
            Vendor approval must be confirmed by the backend. This preview
            cannot approve a shop or publish listings.
          </p>
          <div className="mt-5 flex flex-wrap gap-3">
            <Link href="/vendor/listings" className={action}>
              Browse sample listings
            </Link>
            <Link href="/login?role=vendor" className={ghost}>
              Vendor login preview
            </Link>
          </div>
        </section>
      </div>
    );
  }
  return (
    <>
      <section className="vendor-dark flex flex-col gap-6 rounded-3xl p-7 text-white md:flex-row md:items-center md:justify-between lg:p-9">
        <div>
          <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-bold text-amber-900">
            Sample Vendor · Not verified
          </span>
          <h1 className="vendor-display mt-4 text-4xl font-extrabold">
            Good morning, Akin
          </h1>
          <p className="mt-2 text-slate-300">
            Preview your shop workspace. This sample shop is not live.
          </p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row">
          <Link href="/vendor/listings/new" className={action}>
            + Sell scrap
          </Link>
          <Link href="/vendor/dashboard?view=bulk" className={ghost}>
            Add multiple items
          </Link>
        </div>
      </section>
      <section
        aria-label="Sample overview"
        className="mt-7 grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
      >
        {[
          [
            "Sample active listings",
            String(items.filter((item) => item.status === "Active").length),
            "store",
            "/vendor/listings",
          ],
          ["Pending orders", "—", "orders", "/vendor/dashboard?view=orders"],
          ["Completed sales", "—", "check", "/vendor/dashboard?view=orders"],
          ["Messages", "—", "message", "/vendor/dashboard?view=messages"],
        ].map(([label, value, icon, href]) => (
          <Link href={href} key={label} className="vendor-card p-5">
            <span className="vendor-soft vendor-green grid size-10 place-items-center rounded-xl">
              <VendorIcon name={icon} />
            </span>
            <strong className="vendor-display mt-5 block text-3xl">
              {value}
            </strong>
            <span className="vendor-muted text-sm font-semibold">{label}</span>
          </Link>
        ))}
      </section>
      <div className="mt-8 grid gap-6 lg:grid-cols-[1.25fr_.75fr]">
        <section>
          <div className="flex items-center justify-between">
            <div>
              <p className="vendor-eyebrow">Inventory</p>
              <h2 className="vendor-title">Recent listings</h2>
            </div>
            <Link
              href="/vendor/listings"
              className="vendor-green text-sm font-bold"
            >
              View all
            </Link>
          </div>
          <div className="mt-4 grid gap-3">
            {items.slice(0, 3).map((item) => (
              <Link
                href="/vendor/listings"
                className="vendor-card flex items-center gap-4 p-3"
                key={item.id}
              >
                <ListingPhoto
                  listingId={item.id}
                  category={item.category}
                  title={item.title}
                  compact
                  className="size-16 rounded-xl shrink-0"
                />
                <div className="min-w-0">
                  <h3 className="truncate font-bold">{item.title}</h3>
                  <p className="vendor-green text-sm font-bold">
                    {money(item.price)}
                  </p>
                  <p className="vendor-muted text-xs">Presentation fixture</p>
                </div>
              </Link>
            ))}
          </div>
        </section>
        <aside>
          <p className="vendor-eyebrow">Quick actions</p>
          <h2 className="vendor-title">Manage shop</h2>
          <div className="mt-4 grid gap-3">
            {[
              [
                "My shop location",
                "Ikeja · Sample location",
                "pin",
                "location",
              ],
              [
                "Verification",
                "No verified identity loaded",
                "check",
                "profile",
              ],
              [
                "Store settings",
                "Profile and preferences",
                "settings",
                "settings",
              ],
            ].map(([label, detail, icon, target]) => (
              <Link
                key={target}
                href={`/vendor/dashboard?view=${target}`}
                className="vendor-card flex items-center gap-3 p-3.5"
              >
                <span className="vendor-soft vendor-green grid size-10 shrink-0 place-items-center rounded-xl">
                  <VendorIcon name={icon} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-bold">{label}</span>
                  <span className="vendor-muted mt-0.5 block text-[11px]">
                    {detail}
                  </span>
                </span>
                <span className="vendor-soft rounded-full px-2.5 py-1 text-[10px] font-bold">
                  Manage
                </span>
              </Link>
            ))}
          </div>
        </aside>
      </div>
    </>
  );
}
