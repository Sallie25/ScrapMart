"use client";

import { useEffect, useState } from "react";
import { z } from "zod";
import { BuyerOrders, type BuyerOrder } from "./buyer-orders";

const order = z.object({ id: z.string(), status: z.string(), vendor_business_name: z.string(), currency: z.literal("NGN"),
  total_amount: z.string(), created_at: z.string(), payment_method: z.literal("pay_on_delivery"),
  item: z.object({ title: z.string(), quantity: z.string(), quantity_unit: z.string() }) });
const page = z.object({ orders: z.array(order), next_cursor: z.string().nullable() });

export function BuyerOrderHistory() {
  const [orders, setOrders] = useState<BuyerOrder[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [state, setState] = useState<"loading" | "success" | "error">("loading");
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  async function load(next?: string) {
    setState("loading");
    try {
      const response = await fetch(`/api/account/buyer/orders?limit=20${next ? `&cursor=${encodeURIComponent(next)}` : ""}`, { credentials: "same-origin", cache: "no-store" });
      if (!response.ok) throw new Error();
      const result = page.parse(await response.json());
      setOrders(current => next ? [...current, ...result.orders] : result.orders);
      setCursor(result.next_cursor); setState("success");
    } catch { setState("error"); }
  }
  useEffect(() => { queueMicrotask(() => void load()); }, []);
  async function transition(id: string, action: "cancel" | "complete") {
    if (busy || !window.confirm(action === "complete" ? "Confirm the item was received and the pay-on-delivery order is complete?" : "Cancel this order?")) return;
    setBusy(id); setNotice("");
    try {
      const response = await fetch(`/api/account/buyer/orders/${id}/${action}`, { method: "POST", credentials: "same-origin", cache: "no-store", redirect: "error",
        headers: { "Content-Type": "application/json", "X-ScrapMart-CSRF": "1" }, body: "{}" });
      if (!response.ok) throw new Error();
      setNotice("Order status updated by ScrapMart."); await load();
    } catch { setNotice("Order change was not confirmed. Check the current status before retrying."); }
    finally { setBusy(""); }
  }
  return <><BuyerOrders state={state === "success" ? { status: "success", orders } : { status: state }} />
    {notice && <p role="status" className="buyer-muted mx-auto mt-4 max-w-3xl">{notice}</p>}
    {state === "success" && <div className="mx-auto mt-5 grid max-w-3xl gap-3">{orders.map(item => <div key={item.id} className="flex flex-wrap justify-end gap-2">
      {item.status === "pending" && <button type="button" className="buyer-button buyer-ghost" disabled={!!busy} onClick={() => void transition(item.id, "cancel")}>Cancel {item.item.title}</button>}
      {item.status === "delivered" && <button type="button" className="buyer-button" disabled={!!busy} onClick={() => void transition(item.id, "complete")}>Confirm receipt of {item.item.title}</button>}
    </div>)}</div>}
    {cursor && state === "success" && <button type="button" className="buyer-button mx-auto mt-5 block" onClick={() => void load(cursor)}>Load more orders</button>}
    {state === "error" && <button type="button" className="buyer-button mx-auto mt-5 block" onClick={() => void load()}>Retry</button>}
  </>;
}
