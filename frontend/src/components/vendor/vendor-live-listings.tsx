"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { formatMoney } from "@/lib/marketplace/catalogue";
import { ownedPage, type OwnedListing, vendorRequest } from "@/lib/vendor-listings";

export function VendorLiveListings({ overview = false }: { overview?: boolean }) {
  const [items, setItems] = useState<OwnedListing[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const load = useCallback(async (next?: string) => {
    setLoading(true); setError("");
    try {
      const response = await vendorRequest(`listings?limit=20${next ? `&cursor=${encodeURIComponent(next)}` : ""}`);
      if (!response.ok) throw new Error(response.status === 403 ? "Backend approval and current Vendor evidence are required to manage listings." : "Could not load your listings.");
      const page = ownedPage.parse(await response.json());
      setItems(current => next ? [...current, ...page.listings] : page.listings);
      setCursor(page.next_cursor);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not load your listings."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { queueMicrotask(() => void load()); }, [load]);

  async function transition(item: OwnedListing, action: "publish" | "pause" | "sold" | "delete") {
    if (busy) return;
    if (action === "publish" && !window.confirm("Publish this listing with its approximate location and photos visible to buyers?")) return;
    if (action === "sold" && !window.confirm(`Mark ${item.title} as sold?`)) return;
    if (action === "delete" && !window.confirm(`Archive ${item.title}?`)) return;
    setBusy(item.id); setError("");
    try {
      const response = await vendorRequest(`listings/${item.id}${action === "delete" ? "" : `/${action}`}`, {
        method: action === "delete" ? "DELETE" : "POST",
        ...(action === "delete" ? {} : { headers: { "Content-Type": "application/json" },
          body: JSON.stringify(action === "publish" ? { public_location_consent: true } : {}) }),
      });
      if (!response.ok) throw new Error(response.status === 409 || response.status === 422 ? "Complete the listing, approximate coordinates and stored photo before publishing." :
        response.status === 403 ? "Backend approval and current Vendor evidence are required." : "The listing change was not confirmed.");
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The listing change was not confirmed."); }
    finally { setBusy(""); }
  }

  return <section className="mt-7">
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div><p className="vendor-eyebrow">Your inventory</p><h1 className="vendor-title">{overview ? "Vendor dashboard" : "My Listings"}</h1>
        <p className="vendor-muted mt-2 text-sm">Listings shown here are stored by ScrapMart.</p></div>
      <Link href="/vendor/listings/new" className="vendor-button">+ Sell scrap</Link>
    </div>
    {error && <div role="alert" className="vendor-card mt-5 p-4 text-red-700"><p>{error}</p><Link href="/vendor/dashboard?view=profile" className="mt-3 inline-block text-sm font-bold underline">Review Vendor verification</Link></div>}
    {loading && items.length === 0 ? <p role="status" className="vendor-muted mt-6">Loading listings…</p> :
      !error && items.length === 0 ? <div className="vendor-card mt-6 p-8 text-center"><h2 className="text-xl font-bold">No listings yet</h2><p className="vendor-muted mt-2">Create a listing to get started.</p></div> :
      <div className="mt-6 grid gap-4">{items.map(item => <article key={item.id} className="vendor-card flex flex-wrap items-center justify-between gap-4 p-5">
        <div><h2 className="text-lg font-extrabold">{item.title}</h2><p className="vendor-muted mt-1 text-sm">{item.category?.name ?? "Category needed"} · {item.status}</p>
          {item.price && <p className="vendor-green mt-2 font-bold">{formatMoney(item.price)}</p>}</div>
        <div className="flex flex-wrap gap-2">
          <Link href={`/vendor/listings/${item.id}/edit`} className="vendor-button vendor-ghost">Edit</Link>
          {(item.status === "draft" || item.status === "inactive") && <button type="button" className="vendor-button" disabled={!!busy} onClick={() => void transition(item, "publish")}>Publish</button>}
          {item.status === "active" && <button type="button" className="vendor-button vendor-ghost" disabled={!!busy} onClick={() => void transition(item, "pause")}>Pause</button>}
          {(item.status === "active" || item.status === "inactive") && <button type="button" className="vendor-button vendor-ghost" disabled={!!busy} onClick={() => void transition(item, "sold")}>Mark sold</button>}
          <button type="button" className="vendor-button vendor-ghost" disabled={!!busy} onClick={() => void transition(item, "delete")}>Archive</button>
          {item.status === "active" && <Link href={`/listings/${item.id}`} className="vendor-button vendor-ghost">View public listing</Link>}
        </div>
      </article>)}</div>}
    {cursor && <button type="button" className="vendor-button vendor-ghost mt-5" disabled={loading} onClick={() => void load(cursor)}>Load more</button>}
    {error && <button type="button" className="vendor-button vendor-ghost mt-5" onClick={() => void load()}>Retry</button>}
  </section>;
}
