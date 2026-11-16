"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { claimBuyerSessionRefreshAttempt, clearBuyerSessionRefreshAttempt } from "@/lib/buyer-session-refresh-attempt";

export function BuyerSessionReady() {
  useEffect(() => { clearBuyerSessionRefreshAttempt(sessionStorage); }, []);
  return null;
}

export function BuyerSessionRefresh() {
  const router = useRouter();
  const [failed, setFailed] = useState(false);
  const attempt = useRef<Promise<Response> | null>(null);

  useEffect(() => {
    let active = true;
    attempt.current ??= Promise.resolve().then(() => {
      if (!claimBuyerSessionRefreshAttempt(sessionStorage)) return new Response(null, { status: 409 });
      return fetch("/api/auth/refresh", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
        headers: { "X-ScrapMart-CSRF": "1" },
      });
    });
    void attempt.current.then(response => {
      if (!active) return;
      if (response.status === 200) router.refresh();
      else if (response.status === 401) router.replace("/login?role=buyer");
      else setFailed(true);
    }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [router]);

  return <section role="status" className="buyer-card p-8 text-center">
    <h1 className="buyer-title">{failed ? "Session could not be renewed" : "Renewing your session"}</h1>
    <p className="buyer-muted mt-3">{failed ? "Please sign in again to continue." : "Please wait a moment."}</p>
    {failed && <Link href="/login?role=buyer" className="buyer-button mt-6">Sign in</Link>}
  </section>;
}
