"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
type CaseDetails = Record<string, unknown>;
const showString = (value: unknown) => typeof value === "string" ? value : "Not available";
export default function VerificationCasePage({ params }: { params: Promise<{ vendorId: string }> }) {
  const [id, setId] = useState("");
  const [detail, setDetail] = useState<CaseDetails | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    params.then(async ({ vendorId }) => {
      if (!/^[0-9a-fA-F-]{36}$/.test(vendorId)) throw new Error("Invalid case reference.");
      if (active) setId(vendorId);
      const response = await fetch("/api/auth/verification/cases/" + encodeURIComponent(vendorId), {
        credentials: "same-origin", cache: "no-store",
      });
      if (response.status === 403) throw new Error("Reviewer permission is required; self-review is prohibited.");
      if (response.status === 401) throw new Error("Please sign in to an authorized account.");
      if (!response.ok) throw new Error("Case details are unavailable.");
      return response.json() as Promise<unknown>;
    }).then(value => {
      if (!active) return;
      if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid case details.");
      setDetail(value as CaseDetails);
    }).catch(reason => {
      if (active) setError(reason instanceof Error ? reason.message : "Unable to load case.");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [params]);
  const detailRecord = detail?.case && typeof detail.case === "object" && !Array.isArray(detail.case)
    ? detail.case as CaseDetails : detail;
  return (
    <main className="mx-auto max-w-2xl px-5 py-12">
      <Link className="text-sm font-semibold text-green-700 underline" href="/admin/verification">Back to review queue</Link>
      <h1 className="mt-5 text-3xl font-extrabold">Verification case</h1>
      {id && <p className="mt-3 break-all text-sm text-slate-600">Vendor reference: {id}</p>}
      {loading && <p role="status" className="mt-8">Loading case evidence summary…</p>}
      {error && <p role="alert" className="mt-8 text-red-700">{error}</p>}
      {detailRecord && <section className="mt-7 grid gap-4 rounded-xl border p-6">
        <p><strong>Business:</strong> {showString(detailRecord.business_name)}</p>
        <p><strong>Status:</strong> {showString(detailRecord.verification_status ?? detailRecord.status)}</p>
        <p><strong>Shop location:</strong> {showString(detailRecord.shop_location)}</p>
        <p><strong>Shop address:</strong> {showString(detailRecord.shop_address)}</p>
        <p><strong>Version:</strong> {typeof detailRecord.version === "number" ? detailRecord.version : "Not available"}</p>
        <p><strong>Evidence revision:</strong> {showString(detailRecord.evidence_revision)}</p>
        <p><strong>Identity document available:</strong> {detailRecord.document_available === true ? "Yes" : "Not confirmed"}</p>
        <p className="text-sm text-slate-600">
          Case viewing does not grant approval. Decisions require current evidence, reviewer authorization,
          an explanation, and optimistic concurrency checks.
        </p>
      </section>}
    </main>
  );
}
