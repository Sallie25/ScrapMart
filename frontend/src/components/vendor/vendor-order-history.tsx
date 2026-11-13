"use client";

import { useEffect, useState } from "react";
import { z } from "zod";
import { formatMoney } from "@/lib/marketplace/catalogue";

const order = z.object({ id: z.string(), status: z.string(), total_amount: z.string(),
  payment_method: z.literal("pay_on_delivery"), item: z.object({ title: z.string(), quantity: z.string(), quantity_unit: z.string() }) });
const page = z.object({ orders: z.array(order), next_cursor: z.string().nullable() });
type Order = z.infer<typeof order>;

export function VendorOrderHistory() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  async function load(next?: string) {
    setLoading(true); setError("");
    try {
      const response = await fetch(`/api/account/vendor/orders?limit=20${next ? `&cursor=${encodeURIComponent(next)}` : ""}`, { credentials: "same-origin", cache: "no-store" });
      if (!response.ok) throw new Error(response.status === 403 ? "Current approval and evidence are required to view Vendor orders." : "Orders could not be loaded.");
      const result = page.parse(await response.json());
      setOrders(current => next ? [...current, ...result.orders] : result.orders); setCursor(result.next_cursor);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Orders could not be loaded."); }
    finally { setLoading(false); }
  }
  useEffect(() => { queueMicrotask(() => void load()); }, []);
  async function transition(id: string, action: "accept" | "reject" | "prepare" | "deliver") {
    if (busy || !window.confirm(`Confirm ${action} for this pay-on-delivery order?`)) return;
    setBusy(id); setError("");
    try {
      const response = await fetch(`/api/account/vendor/orders/${id}/${action}`, { method: "POST", credentials: "same-origin", cache: "no-store", redirect: "error",
        headers: { "Content-Type": "application/json", "X-ScrapMart-CSRF": "1" }, body: "{}" });
      if (!response.ok) throw new Error("Order status was not confirmed. Refresh before retrying.");
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Order status was not confirmed."); }
    finally { setBusy(""); }
  }
  return <section className="vendor-card p-6 sm:p-8"><p className="vendor-eyebrow">Vendor workspace</p><h1 className="vendor-title mt-2">Customer Orders</h1>
    <p className="vendor-muted mt-2">Pay on delivery. Only the Buyer can confirm receipt and completion.</p>
    {error && <p role="alert" className="mt-4 text-red-700">{error}</p>}
    {loading && orders.length === 0 && <p role="status" className="vendor-muted mt-5">Loading orders…</p>}
    {!loading && !error && orders.length === 0 && <p className="vendor-muted mt-5">No orders yet.</p>}
    <div className="mt-5 grid gap-4">{orders.map(item => <article key={item.id} className="rounded-xl border border-border p-5">
      <div className="flex flex-wrap justify-between gap-3"><div><h2 className="font-bold">{item.item.title}</h2><p className="vendor-muted mt-1 text-sm">{item.item.quantity} {item.item.quantity_unit} · {item.status}</p>
        <p className="vendor-green mt-2 font-bold">{formatMoney(item.total_amount)}</p></div><div className="flex flex-wrap gap-2">
          {item.status === "pending" && <><button type="button" className="vendor-button" disabled={!!busy} onClick={() => void transition(item.id, "accept")}>Accept</button><button type="button" className="vendor-button vendor-ghost" disabled={!!busy} onClick={() => void transition(item.id, "reject")}>Reject</button></>}
          {item.status === "accepted" && <button type="button" className="vendor-button" disabled={!!busy} onClick={() => void transition(item.id, "prepare")}>Preparing</button>}
          {item.status === "preparing" && <button type="button" className="vendor-button" disabled={!!busy} onClick={() => void transition(item.id, "deliver")}>Mark delivered</button>}
        </div></div></article>)}</div>
    {cursor && <button type="button" className="vendor-button vendor-ghost mt-5" onClick={() => void load(cursor)}>Load more orders</button>}
    {error && <button type="button" className="vendor-button vendor-ghost mt-5" onClick={() => void load()}>Retry</button>}
  </section>;
}
