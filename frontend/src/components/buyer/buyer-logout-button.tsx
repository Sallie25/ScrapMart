"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { buyerLogoutDestination, createBuyerLogoutClient } from "@/lib/buyer-logout";

export function BuyerLogoutButton() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const inFlight = useRef(false);
  const logout = useRef(createBuyerLogoutClient());
  const router = useRouter();

  const submit = async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setPending(true);
    setError("");
    try {
      const result = await logout.current();
      const destination = buyerLogoutDestination(result);
      if (destination) router.replace(destination);
      else setError(result.message);
    } finally {
      inFlight.current = false;
      setPending(false);
    }
  };

  return (
    <>
      <button type="button" className="buyer-nav-link w-full text-left" onClick={() => void submit()} disabled={pending}>
        {pending ? "Signing out…" : "Log out"}
      </button>
      {error && <p role="alert" className="px-3 text-xs text-red-700">{error}</p>}
    </>
  );
}
