"use client";
import Link from "next/link";
import { useState } from "react";

export default function VendorEnrollPage() {
  const [businessName, setBusinessName] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setMessage("");
    try {
      const response = await fetch("/api/auth/vendor/enroll", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-ScrapMart-CSRF": "1" },
        credentials: "same-origin",
        body: JSON.stringify({ business_name: businessName, current_password: currentPassword }),
      });
      setMessage(response.status === 204
        ? "Vendor profile added. Verification is still required."
        : response.status === 401
        ? "Please sign in as a buyer and check your account password."
        : "Vendor enrollment could not be completed.");
    } catch {
      setMessage("Vendor enrollment is temporarily unavailable.");
    } finally {
      setCurrentPassword("");
      setPending(false);
    }
  }
  return (
    <main className="mx-auto max-w-xl px-5 py-12">
      <h1 className="text-3xl font-bold">Become a vendor</h1>
      <p className="mt-3">Already buying with ScrapMart? Sign in to your buyer account and add vendor access without registering a second email.</p>
      <form className="mt-7 grid gap-4" onSubmit={submit}>
        <label className="grid gap-2">Shop or business name
          <input className="rounded-lg border p-3" value={businessName} required maxLength={200} onChange={event => setBusinessName(event.target.value)} />
        </label>
        <label className="grid gap-2">Current account password
          <input className="rounded-lg border p-3" type="password" autoComplete="current-password" value={currentPassword} required onChange={event => setCurrentPassword(event.target.value)} />
        </label>
        <button className="rounded-lg bg-green-700 p-3 font-semibold text-white" disabled={pending}>
          {pending ? "Submitting…" : "Add vendor access"}
        </button>
      </form>
      {message && <p className="mt-4" role="status">{message}</p>}
      <div className="mt-5 flex flex-wrap gap-4">
        <Link className="underline" href="/login?role=buyer">Sign in as buyer</Link>
        <Link className="underline" href="/vendor/verification">Continue to vendor verification</Link>
      </div>
    </main>
  );
}
