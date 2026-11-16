"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

type Shop = {
  business_name: string;
  shop_location: string | null;
  shop_address: string | null;
  verification_status: "pending" | "approved" | "rejected" | "suspended";
};
export default function VendorVerificationPage() {
  const [shop, setShop] = useState<Shop | null>(null);
  const [name, setName] = useState("");
  const [location, setLocation] = useState("");
  const [address, setAddress] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    let active = true;
    fetch("/api/auth/vendor/onboarding", { credentials: "same-origin", cache: "no-store" })
      .then(async response => {
        if (!response.ok) throw new Error(response.status === 401 ? "Sign in to your vendor account to continue." : "We could not load your vendor profile.");
        return response.json() as Promise<Shop>;
      }).then(value => {
        if (!active) return;
        setShop(value);
        setName(value.business_name);
        setLocation(value.shop_location ?? "");
        setAddress(value.shop_address ?? "");
      }).catch(error => { if (active) setMessage(error instanceof Error ? error.message : "Verification is unavailable."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving || !shop) return;
    setSaving(true);
    setMessage("");
    try {
      const response = await fetch("/api/auth/vendor/onboarding", {
        method: "PATCH", credentials: "same-origin", cache: "no-store", redirect: "error",
        headers: { "Content-Type": "application/json", "X-ScrapMart-CSRF": "1" },
        body: JSON.stringify({ business_name: name, shop_location: location, shop_address: address }),
      });
      if (!response.ok) throw new Error(response.status === 403
        ? "This vendor account cannot edit verification details in its current status."
        : response.status === 422 ? "Check the shop name, location, and address." : "Shop details could not be saved.");
      const value: Shop = await response.json();
      setShop(value);
      setMessage("Shop details saved. Document and phone verification are separate requirements.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to save.");
    } finally { setSaving(false); }
  }
  const editable = shop?.verification_status === "pending" || shop?.verification_status === "rejected";
  return (
    <main className="mx-auto max-w-2xl px-5 py-12">
      <p className="text-sm font-semibold text-green-700">Vendor verification</p>
      <h1 className="mt-2 text-3xl font-extrabold">Verify your shop</h1>
      <p className="mt-3 text-sm text-slate-600">
        Your shop details are private onboarding information. Saving them does not submit a verification request or approve your account.
      </p>
      {loading && <p role="status" className="mt-6">Loading vendor details…</p>}
      {shop && <p className="mt-5 text-sm font-semibold">Current verification status: {shop.verification_status}</p>}
      {shop && <form onSubmit={save} className="mt-6 grid gap-4">
        <label className="grid gap-2 text-sm font-semibold">Business / shop name
          <input className="rounded-xl border p-3" value={name} maxLength={200} required disabled={!editable || saving} onChange={event => setName(event.target.value)} />
        </label>
        <label className="grid gap-2 text-sm font-semibold">Shop location
          <input className="rounded-xl border p-3" value={location} maxLength={200} required disabled={!editable || saving} onChange={event => setLocation(event.target.value)} placeholder="e.g. Ikeja, Lagos" />
        </label>
        <label className="grid gap-2 text-sm font-semibold">Shop address
          <textarea className="rounded-xl border p-3" value={address} maxLength={500} required disabled={!editable || saving} onChange={event => setAddress(event.target.value)} rows={3} />
        </label>
        <button disabled={!editable || saving} className="rounded-xl bg-green-700 px-5 py-3 font-bold text-white disabled:opacity-60">
          {saving ? "Saving…" : "Save shop details"}
        </button>
      </form>}
      {message && <p role="status" className="mt-5 text-sm">{message}</p>}
      <p className="mt-6 text-sm text-slate-600">
        Identity-image upload, phone ownership verification, and formal reviewer submission must also be completed before approval.
      </p>
      <Link href="/vendor/dashboard?view=profile" className="mt-4 inline-block font-semibold text-green-700 underline">Back to vendor profile</Link>
    </main>
  );
}
