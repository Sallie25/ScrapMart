"use client";

import { useEffect, useState, type FormEvent } from "react";
import { z } from "zod";
import { vendorRequest } from "@/lib/vendor-listings";

const shop = z.object({ business_name: z.string(), shop_location: z.string().nullable(),
  shop_address: z.string().nullable(), verification_status: z.enum(["pending", "approved", "rejected", "suspended"]) });
type Shop = z.infer<typeof shop>;

export function VendorShopProfile() {
  const [profile, setProfile] = useState<Shop | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [verificationNotice, setVerificationNotice] = useState("");
  const [verificationError, setVerificationError] = useState("");
  useEffect(() => {
    let active = true;
    void vendorRequest("onboarding").then(async response => {
      if (!response.ok) throw new Error();
      const value = shop.parse(await response.json());
      if (active) setProfile(value);
    }).catch(() => { if (active) setError("Shop information could not be loaded."); });
    return () => { active = false; };
  }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return;
    setBusy(true); setSaved(false); setError("");
    const data = new FormData(event.currentTarget);
    const body = { business_name: String(data.get("business_name") ?? "").trim(),
      shop_location: String(data.get("shop_location") ?? "").trim(),
      shop_address: String(data.get("shop_address") ?? "").trim() };
    try {
      const response = await vendorRequest("onboarding", { method: "PATCH",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!response.ok) throw new Error(response.status === 403 ? "Backend rules do not permit changes in this verification state." : "Shop information was not saved.");
      setProfile(shop.parse(await response.json())); setSaved(true);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Shop information was not saved."); }
    finally { setBusy(false); }
  }
  async function submitDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return;
    const data = new FormData(event.currentTarget);
    const file = data.get("identity_document");
    const kind = String(data.get("identification_type") ?? "");
    if (!(file instanceof File) || !file.size || file.size > 3 * 1024 * 1024 || !["image/jpeg", "image/png"].includes(file.type)) {
      setVerificationError("Choose a JPEG or PNG document no larger than 3 MB."); return;
    }
    setBusy(true); setVerificationNotice(""); setVerificationError("");
    try {
      const response = await vendorRequest(`identity-document?identification_type=${encodeURIComponent(kind)}`, {
        method: "POST", headers: { "Content-Type": file.type }, body: file,
      });
      if (response.status !== 202) throw new Error("Identity document submission was not confirmed.");
      setVerificationNotice("Document submitted for private review. Approval is still pending.");
    } catch (reason) { setVerificationError(reason instanceof Error ? reason.message : "Document submission failed."); }
    finally { setBusy(false); }
  }
  async function phoneOperation(action: "send-code" | "verify-code", code?: string) {
    if (busy) return;
    setBusy(true); setVerificationNotice(""); setVerificationError("");
    try {
      const response = await vendorRequest(`phone/${action}`, { method: "POST",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(action === "send-code" ? {} : { code }) });
      if (response.status !== (action === "send-code" ? 202 : 204)) throw new Error(action === "send-code" ? "Code delivery was not confirmed." : "Phone verification failed. Check the code and try again.");
      setVerificationNotice(action === "send-code" ? "If delivery is available, a verification code will be sent." : "Phone number verified. Vendor approval still requires identity review.");
    } catch (reason) { setVerificationError(reason instanceof Error ? reason.message : "Phone verification request failed."); }
    finally { setBusy(false); }
  }
  if (!profile) return <section role={error ? "alert" : "status"} className="vendor-card p-8">{error || "Loading shop information…"}</section>;
  const editable = profile.verification_status === "pending" || profile.verification_status === "rejected";
  return <section className="vendor-card mx-auto max-w-3xl p-7 sm:p-10">
    <p className="vendor-eyebrow">Vendor account</p><h1 className="vendor-title mt-2">Shop information</h1>
    <p className="vendor-muted mt-3">Verification status: <strong>{profile.verification_status}</strong>. Updating shop details does not submit identity evidence or approve your account.</p>
    {error && <p role="alert" className="mt-4 text-red-700">{error}</p>}
    {saved && <p role="status" className="mt-4 text-green-800">Shop information saved by ScrapMart.</p>}
    <form onSubmit={submit} className="mt-6 grid gap-5">
      <label className="grid gap-2 text-sm font-bold">Business name<input name="business_name" required maxLength={200} defaultValue={profile.business_name} disabled={!editable} className="rounded-md border border-border p-3" /></label>
      <label className="grid gap-2 text-sm font-bold">Shop location<input name="shop_location" required maxLength={200} defaultValue={profile.shop_location ?? ""} disabled={!editable} className="rounded-md border border-border p-3" /></label>
      <label className="grid gap-2 text-sm font-bold">Shop address<input name="shop_address" required maxLength={500} defaultValue={profile.shop_address ?? ""} disabled={!editable} className="rounded-md border border-border p-3" /></label>
      {editable && <button type="submit" disabled={busy} className="vendor-button">{busy ? "Saving…" : "Save shop information"}</button>}
    </form>
    {editable && <div className="mt-10 border-t border-border pt-7">
      <h2 className="text-xl font-bold">Verification</h2><p className="vendor-muted mt-2 text-sm">Submission does not grant approval. A reviewer must approve the account before selling.</p>
      {verificationNotice && <p role="status" className="mt-4 text-green-800">{verificationNotice}</p>}
      {verificationError && <p role="alert" className="mt-4 text-red-700">{verificationError}</p>}
      <form onSubmit={submitDocument} className="mt-5 grid gap-4">
        <label className="grid gap-2 text-sm font-bold">Identification type<select name="identification_type" className="rounded-md border border-border p-3"><option value="national_id">National ID</option><option value="passport">Passport</option><option value="drivers_license">Driver&apos;s licence</option><option value="voter_id">Voter ID</option></select></label>
        <label className="grid gap-2 text-sm font-bold">Private identity document<input name="identity_document" type="file" accept="image/jpeg,image/png" required className="rounded-md border border-border p-3" /></label>
        <button type="submit" disabled={busy} className="vendor-button">Submit document for review</button>
      </form>
      <div className="mt-7 grid gap-4"><button type="button" disabled={busy} onClick={() => void phoneOperation("send-code")} className="vendor-button vendor-ghost">Send phone code</button>
        <form onSubmit={event => { event.preventDefault(); const code = String(new FormData(event.currentTarget).get("code") ?? ""); void phoneOperation("verify-code", code); }} className="flex flex-wrap gap-3">
          <input name="code" aria-label="Six-digit phone code" required pattern="[0-9]{6}" inputMode="numeric" maxLength={6} className="min-w-0 flex-1 rounded-md border border-border p-3" />
          <button type="submit" disabled={busy} className="vendor-button">Verify phone</button>
        </form></div>
    </div>}
  </section>;
}
