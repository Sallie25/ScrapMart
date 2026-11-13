"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { z } from "zod";

const conversation = z.object({ id: z.string(), listing_id: z.string(), unread_count: z.number().int() });
const list = z.object({ conversations: z.array(conversation), next_cursor: z.string().nullable() });
const message = z.object({ id: z.string(), content: z.string(), sender: z.enum(["buyer", "vendor"]), created_at: z.string(), read_at: z.string().nullable() });
const history = z.object({ messages: z.array(message), next_cursor: z.string().nullable() });
type Conversation = z.infer<typeof conversation>;
type Message = z.infer<typeof message>;

async function account(path: string, options: RequestInit = {}) {
  const headers = new Headers(options.headers);
  if (options.method === "POST") { headers.set("Content-Type", "application/json"); headers.set("X-ScrapMart-CSRF", "1"); }
  return fetch(`/api/account/${path}`, { credentials: "same-origin", cache: "no-store", redirect: "error", ...options, headers });
}

export function AccountMessages({ role }: { role: "buyer" | "vendor" }) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [content, setContent] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [cursor, setCursor] = useState<string | null>(null);
  const requestId = useRef<string | null>(null);
  useEffect(() => {
    let active = true;
    void account("conversations?limit=20").then(async response => {
      if (!response.ok) throw new Error();
      const result = list.parse(await response.json());
      if (active) { setConversations(result.conversations); setCursor(result.next_cursor); }
    }).catch(() => { if (active) setError("Conversations could not be loaded."); })
      .finally(() => { if (active) setLoadingList(false); });
    return () => { active = false; };
  }, []);
  async function more() {
    if (!cursor) return;
    setLoadingList(true); setError("");
    try {
      const response = await account(`conversations?limit=20&cursor=${encodeURIComponent(cursor)}`);
      if (!response.ok) throw new Error();
      const result = list.parse(await response.json());
      setConversations(current => [...current, ...result.conversations]); setCursor(result.next_cursor);
    } catch { setError("More conversations could not be loaded."); }
    finally { setLoadingList(false); }
  }
  async function open(id: string) {
    setSelected(id); setMessages([]); setLoadingMessages(true); setError("");
    try {
      const response = await account(`conversations/${id}/messages?limit=100`);
      if (!response.ok) throw new Error();
      setMessages(history.parse(await response.json()).messages);
    } catch { setError("Messages could not be loaded."); }
    finally { setLoadingMessages(false); }
  }
  async function send() {
    if (!selected || !content.trim() || busy) return;
    setBusy(true); setError(""); setNotice("");
    requestId.current ??= crypto.randomUUID();
    try {
      const response = await account(`conversations/${selected}/messages`, { method: "POST",
        body: JSON.stringify({ content: content.trim(), request_id: requestId.current }) });
      if (response.status !== 201) throw new Error();
      requestId.current = null; setContent(""); setNotice("Message sent."); await open(selected);
    } catch { setError("Message was not confirmed. Retry without changing the text, or check the conversation first."); }
    finally { setBusy(false); }
  }
  async function markRead(id: string) {
    if (!selected || busy) return;
    setBusy(true); setError("");
    try {
      const response = await account(`conversations/${selected}/read`, { method: "POST", body: JSON.stringify({ message_id: id }) });
      if (!response.ok) throw new Error();
      await open(selected);
    } catch { setError("Read status was not confirmed."); }
    finally { setBusy(false); }
  }
  return <section className={role === "buyer" ? "buyer-card p-6 sm:p-8" : "vendor-card p-6 sm:p-8"}>
    <h1 className={role === "buyer" ? "buyer-title" : "vendor-title"}>Messages</h1>
    {error && <p role="alert" className="mt-4 text-red-700">{error}</p>}
    {notice && <p role="status" className="mt-4 text-green-800">{notice}</p>}
    <div className="mt-6 grid gap-5 lg:grid-cols-[16rem_1fr]"><nav aria-label="Conversations" className="grid content-start gap-2">
      {loadingList && conversations.length === 0 && <p role="status" className="text-sm text-muted">Loading conversations…</p>}
      {!loadingList && !error && conversations.length === 0 && <p className="text-sm text-muted">No conversations yet.</p>}
      {conversations.map(item => <button type="button" key={item.id} onClick={() => void open(item.id)}
        className="rounded-xl border border-border p-3 text-left text-sm" aria-current={selected === item.id ? "true" : undefined}>
        Listing {item.listing_id.slice(0, 8)} · {item.unread_count} unread</button>)}
      {cursor && <button type="button" disabled={loadingList} onClick={() => void more()} className="text-left text-sm font-bold text-primary">Load more</button>}
    </nav><div>
      {selected ? <><Link href={`/listings/${conversations.find(item => item.id === selected)?.listing_id ?? ""}`} className="text-sm font-bold text-primary">View listing</Link>
        {loadingMessages && <p role="status" className="mt-4 text-sm text-muted">Loading messages…</p>}
        <div className="mt-4 grid max-h-[28rem] gap-3 overflow-y-auto">{messages.map(item => <article key={item.id} className="rounded-xl border border-border p-3 text-sm">
          <p className="font-bold">{item.sender === role ? "You" : item.sender}</p><p className="mt-2 whitespace-pre-wrap">{item.content}</p>
          {item.sender !== role && !item.read_at && <button type="button" disabled={busy} onClick={() => void markRead(item.id)} className="mt-2 text-primary underline">Mark read</button>}
        </article>)}</div>
        <form onSubmit={event => { event.preventDefault(); void send(); }} className="mt-5 grid gap-3">
          <textarea value={content} onChange={event => { setContent(event.target.value); requestId.current = null; }} maxLength={4000} required rows={3}
            aria-label="Message" className="rounded-md border border-border p-3" />
          <button type="submit" disabled={busy || !content.trim()} className={role === "buyer" ? "buyer-button" : "vendor-button"}>Send message</button>
        </form></> : <p className="text-sm text-muted">Select a conversation to read and reply.</p>}
    </div></div>
  </section>;
}
