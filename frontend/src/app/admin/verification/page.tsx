"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

type CaseSummary = {
  vendor_id: string;
  business_name?: string;
  verification_status?: string;
  submitted_at?: string | null;
};
const extractCases = (value: unknown): CaseSummary[] => {
  if (!value || typeof value !== "object" || Array.isArray(value)) return [];
  const object = value as Record<string, unknown>;
  const rows = object.cases ?? object.items ?? object.results;
  if (!Array.isArray(rows)) return [];
  return rows.flatMap((entry): CaseSummary[] => {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) return [];
    const data = entry as Record<string, unknown>;
    if (typeof data.vendor_id !== "string" || !/^[0-9a-fA-F-]{36}$/.test(data.vendor_id)) return [];
    return [{
      vendor_id: data.vendor_id,
      business_name: typeof data.business_name === "string" ? data.business_name : undefined,
      verification_status: typeof data.verification_status === "string" ? data.verification_status : undefined,
      submitted_at: typeof data.submitted_at === "string" ? data.submitted_at : null,
    }];
  });
};
export default function VerificationReviewPage() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    fetch("/api/auth/verification/cases?status=pending&limit=25", { credentials: "same-origin", cache: "no-store" })
      .then(async response => {
        if (response.status === 403) throw new Error("This account does not have verification reviewer permission.");
        if (response.status === 401) throw new Error("Please sign in to an authorized ScrapMart account.");
        if (!response.ok) throw new Error("The verification queue is unavailable.");
        return response.json() as Promise<unknown>;
      })
      .then(value => { if (active) setCases(extractCases(value)); })
      .catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "Unable to load cases."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  return (
    <main className="mx-auto max-w-4xl px-5 py-12">
      <p className="text-sm font-semibold text-green-700">Restricted review workspace</p>
      <h1 className="mt-2 text-3xl font-extrabold">Vendor verification cases</h1>
      <p className="mt-3 text-sm text-slate-600">
        This queue requires an active session and separately provisioned reviewer permission.
        A shop cannot be approved merely by changing its displayed status.
      </p>
      {loading && <p role="status" className="mt-8">Loading pending verification cases…</p>}
      {error && <p role="alert" className="mt-8 text-red-700">{error}</p>}
      {!loading && !error && cases.length === 0 && <p className="mt-8">No pending cases were returned in the supported queue format.</p>}
      <div className="mt-7 grid gap-3">
        {cases.map(item => <article className="rounded-xl border p-5" key={item.vendor_id}>
          <h2 className="font-bold">{item.business_name || "Vendor verification"}</h2>
          <p className="mt-1 text-sm text-slate-600">Case reference: {item.vendor_id}</p>
          {item.submitted_at && <p className="mt-1 text-sm">Submitted: {item.submitted_at}</p>}
          <Link className="mt-3 inline-block font-semibold text-green-700 underline"
            href={"/admin/verification/" + item.vendor_id}>Inspect case</Link>
        </article>)}
      </div>
    </main>
  );
}
