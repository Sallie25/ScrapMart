"use client";

import { useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { buyerActionLogin } from "@/lib/marketplace/buyer-actions";
import type { CatalogueListing } from "@/lib/marketplace/catalogue";
import { formatQuantity } from "@/lib/marketplace/catalogue";

async function accountPost(path: string, body: unknown) {
  return fetch(`/api/account/${path}`, { method: "POST", credentials: "same-origin", cache: "no-store",
    redirect: "error", headers: { "Content-Type": "application/json", "X-ScrapMart-CSRF": "1" }, body: JSON.stringify(body) });
}

export function ListingInteractions({ listing }: { listing: CatalogueListing }) {
  const router = useRouter();
  const [quantity, setQuantity] = useState(listing.price_type === "total" ? listing.quantity : "1");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const orderId = useRef<string | null>(null);
  const messageId = useRef<string | null>(null);

  async function placeOrder(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return;
    if (!window.confirm("Place a pay-on-delivery order? No payment will be collected now.")) return;
    setBusy(true); setError(""); setNotice("");
    orderId.current ??= crypto.randomUUID();
    try {
      const response = await accountPost("buyer/orders", { listing_id: listing.id, request_id: orderId.current, quantity });
      if (response.status === 401) { router.push(buyerActionLogin(listing.id, "order")); return; }
      if (response.status !== 201) throw new Error(response.status === 409 ? "This quantity or listing is no longer available." : "Order was not confirmed. Retry with the same details, or check My Orders.");
      const payload: unknown = await response.json();
      if (!payload || typeof payload !== "object" || !("id" in payload) || typeof payload.id !== "string") throw new Error("Order response could not be confirmed. Check My Orders.");
      orderId.current = null;
      setNotice("Pay-on-delivery order placed. Payment is due only when the item is delivered.");
      router.refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Order was not confirmed."); }
    finally { setBusy(false); }
  }

  async function contact(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy || !message.trim()) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const started = await accountPost("conversations", { listing_id: listing.id });
      if (started.status === 401) { router.push(buyerActionLogin(listing.id, "contact")); return; }
      if (started.status !== 201) throw new Error("Conversation could not be started.");
      const conversation: unknown = await started.json();
      if (!conversation || typeof conversation !== "object" || !("id" in conversation) || typeof conversation.id !== "string") throw new Error("Conversation could not be confirmed.");
      messageId.current ??= crypto.randomUUID();
      const sent = await accountPost(`conversations/${conversation.id}/messages`, { content: message.trim(), request_id: messageId.current });
      if (sent.status !== 201) throw new Error("Conversation was created, but your message was not confirmed. Retry from Messages.");
      setMessage(""); messageId.current = null;
      setNotice("Message sent to the vendor.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Message was not confirmed."); }
    finally { setBusy(false); }
  }

  return <div className="buyer-soft mt-6 rounded-2xl p-5">
    <p className="buyer-eyebrow">Buying this item</p><h2 className="mt-1 text-xl font-extrabold">Contact and ordering</h2>
    <p className="buyer-muted mt-1 text-sm">Orders use pay on delivery. No online payment is collected.</p>
    {error && <p role="alert" className="mt-4 text-sm text-red-700">{error}</p>}
    {notice && <p role="status" className="mt-4 text-sm text-green-800">{notice}</p>}
    <form onSubmit={placeOrder} className="mt-5 flex flex-wrap items-end gap-3">
      <label className="grid gap-1 text-sm font-bold">Quantity ({formatQuantity(listing.available_quantity)} available)
        <input type="text" inputMode="decimal" required pattern="[0-9]+([.][0-9]{1,3})?" value={quantity}
          disabled={listing.price_type === "total"} onChange={event => { setQuantity(event.target.value); orderId.current = null; }}
          className="w-36 rounded-md border border-border bg-white p-3" /></label>
      <button type="submit" disabled={busy} className="buyer-button">Place pay-on-delivery order</button>
    </form>
    <form onSubmit={contact} className="mt-5 grid gap-3"><label className="grid gap-1 text-sm font-bold">Message vendor
      <textarea value={message} onChange={event => { setMessage(event.target.value); messageId.current = null; }} required maxLength={4000}
        rows={3} className="rounded-md border border-border bg-white p-3" placeholder="Ask a question about this listing" /></label>
      <button type="submit" disabled={busy || !message.trim()} className="buyer-button buyer-ghost">Send message</button></form>
  </div>;
}
