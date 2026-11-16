"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import type { CatalogueCategory } from "@/lib/marketplace/catalogue";
import { ownedListing, type OwnedListing, vendorRequest } from "@/lib/vendor-listings";

const conditions = [
  ["good_condition", "Good condition"], ["used", "Used"], ["faulty", "Faulty"],
  ["damaged", "Damaged"], ["for_parts", "For parts"],
] as const;
const units = [["pieces", "Piece"], ["kilograms", "Kilogram"], ["tonnes", "Tonne"], ["bundles", "Bundle"]] as const;

export function VendorListingForm({ categories, listingId }: { categories: CatalogueCategory[]; listingId?: string }) {
  const [initial, setInitial] = useState<OwnedListing | null>(null);
  const [loading, setLoading] = useState(!!listingId);
  const [error, setError] = useState("");
  const [result, setResult] = useState<{ id: string; published: boolean; message: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const router = useRouter();
  useEffect(() => {
    if (!listingId) return;
    let active = true;
    void vendorRequest(`listings/${listingId}`).then(async response => {
      if (!response.ok) throw new Error("Could not load this listing.");
      const listing = ownedListing.parse(await response.json());
      if (active) setInitial(listing);
    }).catch(() => { if (active) setError("Could not load this listing."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [listingId]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setError(""); setResult(null); setBusy(true);
    const data = new FormData(event.currentTarget);
    const value = (key: string) => String(data.get(key) ?? "").trim();
    const photo = data.get("photo") instanceof File ? data.get("photo") as File : null;
    const consent = data.get("publicConsent") === "on";
    const body = {
      title: value("title"), category_id: value("category_id"), description: value("description"),
      price: value("price"), price_type: "per_unit", quantity: value("quantity"),
      quantity_unit: value("quantity_unit"), condition: value("condition"),
      location_summary: value("location_summary"),
      latitude: value("latitude") || null, longitude: value("longitude") || null,
      location_visibility: "approximate", public_location_consent: consent,
    };
    if (!body.title || !body.category_id || !body.description || !body.price || !body.quantity ||
      !body.quantity_unit || !body.condition || !body.location_summary) {
      setError("Complete all required listing fields."); setBusy(false); return;
    }
    if ((body.latitude === null) !== (body.longitude === null)) {
      setError("Provide both latitude and longitude, or leave both blank for a draft."); setBusy(false); return;
    }
    if (photo && photo.size && (!["image/jpeg", "image/png"].includes(photo.type) || photo.size > 3 * 1024 * 1024)) {
      setError("Choose a JPEG or PNG photo no larger than 3 MB."); setBusy(false); return;
    }
    let savedId = listingId;
    try {
      const response = await vendorRequest(listingId ? `listings/${listingId}` : "listings", {
        method: listingId ? "PATCH" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      if (!response.ok) throw new Error(response.status === 403 ? "Current backend approval and Vendor evidence are required to save listings." : "Listing was not saved. Check the fields and try again.");
      const saved = ownedListing.parse(await response.json());
      savedId = saved.id;
      if (photo && photo.size && consent) {
        const upload = await vendorRequest(`listings/${saved.id}/photos?public_consent=true`, {
          method: "POST", headers: { "Content-Type": photo.type }, body: photo,
        });
        if (!upload.ok) throw new Error("Listing was saved as a draft, but its photo was not stored. Open Edit to retry.");
      }
      const hasPhoto = saved.photos.length > 0 || !!(photo && photo.size && consent);
      if (consent && hasPhoto && body.latitude && body.longitude) {
        const published = await vendorRequest(`listings/${saved.id}/publish`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ public_location_consent: true }),
        });
        if (!published.ok) throw new Error("Listing was saved, but publication was not confirmed. Open My Listings to complete it.");
        setResult({ id: saved.id, published: true, message: "Listing published. Buyers can now find it in the live marketplace." });
      } else setResult({ id: saved.id, published: false, message: "Listing saved as a draft. Add a photo, approximate coordinates, and public consent to publish." });
      router.refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Listing operation failed.");
      if (savedId) setResult({ id: savedId, published: false, message: "A saved listing may need attention in My Listings." });
    } finally { setBusy(false); }
  }

  if (loading) return <p role="status" className="vendor-muted p-6">Loading listing…</p>;
  if (listingId && !initial) return <p role="alert" className="vendor-card p-6">{error || "Listing unavailable."}</p>;
  if (initial?.status === "active") return <section className="vendor-card p-6"><h1 className="vendor-title">Pause this listing to edit it</h1><Link href="/vendor/listings" className="vendor-button mt-5">My Listings</Link></section>;
  if (initial?.status === "sold" || initial?.status === "removed") return <section className="vendor-card p-6"><h1 className="vendor-title">This listing cannot be edited</h1><Link href="/vendor/listings" className="vendor-button mt-5">My Listings</Link></section>;
  return <div className="vendor-add rounded-3xl bg-white p-6 shadow-sm md:p-8">
    <Link href="/vendor/listings" className="text-sm font-medium text-primary hover:underline">← Back to listings</Link>
    <div className="mt-5"><p className="text-sm font-medium text-primary">VENDOR WORKSPACE</p><h1 className="mt-2 text-3xl font-bold tracking-tight text-text">{listingId ? "Edit listing" : "Sell scrap"}</h1>
      <p className="mt-2 leading-6 text-muted">Save a draft or publish to the live marketplace after approval and consent.</p></div>
    {result && <section role="status" className="mt-6 rounded-xl border border-border bg-surface p-5"><p>{result.message}</p>
      <div className="mt-4 flex gap-3"><Link href="/vendor/listings" className="vendor-button">My Listings</Link>{result.published && <Link href={`/listings/${result.id}`} className="vendor-button vendor-ghost">View public listing</Link>}</div></section>}
    {error && <p role="alert" className="mt-5 rounded-xl border border-red-200 bg-red-50 p-4 text-red-700">{error}</p>}
    <form onSubmit={submit} key={initial?.id ?? "new"} className="mt-7 space-y-5">
      <label className="block text-sm font-semibold">Item name *<input name="title" required maxLength={200} defaultValue={initial?.title ?? ""} className="mt-2 w-full rounded-md border border-border p-3" /></label>
      <div className="grid gap-5 sm:grid-cols-2">
        <label className="block text-sm font-semibold">Category *<select name="category_id" required defaultValue={initial?.category_id ?? ""} className="mt-2 w-full rounded-md border border-border p-3"><option value="">Select a category</option>{categories.map(category => <option value={category.id} key={category.id}>{category.name}</option>)}</select></label>
        <label className="block text-sm font-semibold">Condition *<select name="condition" required defaultValue={initial?.condition ?? ""} className="mt-2 w-full rounded-md border border-border p-3"><option value="">Select condition</option>{conditions.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      </div>
      <label className="block text-sm font-semibold">Description *<textarea name="description" required minLength={10} maxLength={5000} defaultValue={initial?.description ?? ""} rows={4} className="mt-2 w-full rounded-md border border-border p-3" /></label>
      <div className="grid gap-5 sm:grid-cols-3">
        <label className="block text-sm font-semibold">Price per unit in naira *<input name="price" required inputMode="decimal" pattern="[0-9]+([.][0-9]{1,2})?" defaultValue={initial?.price ?? ""} className="mt-2 w-full rounded-md border border-border p-3" /></label>
        <label className="block text-sm font-semibold">Quantity *<input name="quantity" required inputMode="decimal" pattern="[0-9]+([.][0-9]{1,3})?" defaultValue={initial?.quantity ?? ""} className="mt-2 w-full rounded-md border border-border p-3" /></label>
        <label className="block text-sm font-semibold">Unit *<select name="quantity_unit" required defaultValue={initial?.quantity_unit ?? "kilograms"} className="mt-2 w-full rounded-md border border-border p-3">{units.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      </div>
      <label className="block text-sm font-semibold">Approximate location *<input name="location_summary" required maxLength={255} defaultValue={initial?.location_summary ?? ""} placeholder="e.g. Ikeja, Lagos" className="mt-2 w-full rounded-md border border-border p-3" /></label>
      <div className="grid gap-5 sm:grid-cols-2">
        <label className="block text-sm font-semibold">Latitude for publication<input name="latitude" inputMode="decimal" defaultValue={initial?.latitude ?? ""} placeholder="6.601800" className="mt-2 w-full rounded-md border border-border p-3" /></label>
        <label className="block text-sm font-semibold">Longitude for publication<input name="longitude" inputMode="decimal" defaultValue={initial?.longitude ?? ""} placeholder="3.351500" className="mt-2 w-full rounded-md border border-border p-3" /></label>
      </div>
      <label className="block text-sm font-semibold">Material photo {initial?.photos.length ? "(optional replacement)" : "(required to publish)"}<input name="photo" type="file" accept="image/jpeg,image/png" className="mt-2 block w-full rounded-md border border-border p-3" /></label>
      <label className="flex items-start gap-3 text-sm"><input name="publicConsent" type="checkbox" className="mt-1" /><span>I consent to show this listing’s approximate location and uploaded photo publicly when published.</span></label>
      <p className="text-sm text-muted">ScrapMart uses pay on delivery. No payment is collected here.</p>
      <button type="submit" disabled={busy || categories.length === 0} className="vendor-button w-full">{busy ? "Saving…" : "Save listing"}</button>
    </form>
  </div>;
}
