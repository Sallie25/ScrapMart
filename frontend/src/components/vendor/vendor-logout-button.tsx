"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { createBuyerLogoutClient } from "@/lib/buyer-logout";
import { markConfirmedLogout } from "@/lib/logout-feedback";

export function VendorLogoutButton() {
  const router = useRouter();
  const client = useRef(createBuyerLogoutClient());
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  async function logout() {
    if (pending) return;
    setPending(true); setError("");
    const result = await client.current();
    if (result.status === "confirmed" || result.status === "already_signed_out") {
      if (result.status === "confirmed") markConfirmedLogout("vendor");
      router.refresh(); router.replace("/login?role=vendor");
    }
    else setError(result.message);
    setPending(false);
  }
  return <div><button type="button" onClick={() => void logout()} disabled={pending} className="vendor-nav-link w-full text-left">{pending ? "Signing out…" : "Sign out"}</button>{error && <div className="px-3 text-xs text-red-700"><p role="alert">{error}</p><button type="button" className="underline" onClick={() => void logout()} disabled={pending}>Retry</button></div>}</div>;
}
