"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { createBuyerLogoutClient } from "@/lib/buyer-logout";

export function VendorLogoutButton() {
  const router = useRouter();
  const client = useRef(createBuyerLogoutClient());
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  async function logout() {
    if (pending) return;
    setPending(true); setError("");
    const result = await client.current();
    if (result.status === "confirmed") router.replace("/login?role=vendor");
    else setError(result.message);
    setPending(false);
  }
  return <div><button type="button" onClick={() => void logout()} disabled={pending} className="vendor-nav-link w-full text-left">{pending ? "Signing out…" : "Sign out"}</button>{error && <p role="alert" className="px-3 text-xs text-red-700">{error}</p>}</div>;
}
