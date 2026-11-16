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
  const [reason, setReason] = useState("");
  const [deciding, setDeciding] = useState(false);
  const [decisionMessage, setDecisionMessage] = useState("");
  const [decisionRecorded, setDecisionRecorded] = useState(false);
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
  const version = detailRecord?.version;
  const evidenceRevision = detailRecord?.evidence_revision;
  const decisionReady = typeof version === "number" && Number.isSafeInteger(version) && version >= 0 &&
    typeof evidenceRevision === "string" && evidenceRevision.length > 0 && evidenceRevision.length <= 256;
  async function decide(action: "approve" | "reject") {
    if (!decisionReady || deciding || decisionRecorded || reason.trim().length === 0 || reason.length > 500) return;
    setDeciding(true);
    setDecisionMessage("");
    try {
      const response = await fetch("/api/auth/verification/cases/" + encodeURIComponent(id) + "/" + action, {
        method: "POST", credentials: "same-origin", cache: "no-store", redirect: "error",
        headers: { "Content-Type": "application/json", "X-ScrapMart-CSRF": "1" },
        body: JSON.stringify({
          expected_version: version, expected_evidence_revision: evidenceRevision, reason: reason.trim(),
        }),
      });
      if (response.ok) {
        const value: unknown = await response.json();
        if (!value || typeof value !== "object" || !("decision_recorded" in value) ||
            value.decision_recorded !== true) throw new Error("The decision outcome could not be confirmed.");
        setDecisionRecorded(true);
        setDecisionMessage("Decision recorded by the verification service. Return to the queue to view updated cases.");
      } else {
        setDecisionMessage(response.status === 409 ? "This case changed. Reload it before deciding." :
          response.status === 403 ? "Reviewer permission denied or self-review is prohibited." :
          response.status === 401 ? "Your session expired. Sign in again." :
          "The decision could not be recorded. Check evidence and reviewer authorization.");
      }
    } catch { setDecisionMessage("The decision could not be confirmed. Reload the case before retrying."); }
    finally { setDeciding(false); }
  }
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
      {detailRecord && <section className="mt-7 rounded-xl border p-6">
        <h2 className="text-xl font-bold">Reviewer decision</h2>
        <p className="mt-2 text-sm text-slate-600">
          Approve only after reviewing complete, current evidence. Decisions are audited on the backend.
          A stale version or changed evidence will be rejected.
        </p>
        {!decisionReady && <p className="mt-3 text-sm text-amber-700">
          Versioned evidence data is unavailable; decisions are disabled for this case.
        </p>}
        <label className="mt-4 grid gap-2 text-sm font-semibold">
          Reason for decision (required)
          <textarea rows={3} maxLength={500} value={reason}
            onChange={event => setReason(event.target.value)}
            disabled={!decisionReady || deciding || decisionRecorded}
            className="rounded-xl border p-3" />
        </label>
        <div className="mt-5 flex flex-wrap gap-3">
          <button type="button" onClick={() => void decide("approve")}
            disabled={!decisionReady || deciding || decisionRecorded || !reason.trim()}
            className="rounded-xl bg-green-700 px-5 py-3 font-bold text-white disabled:opacity-60">
            Approve vendor
          </button>
          <button type="button" onClick={() => void decide("reject")}
            disabled={!decisionReady || deciding || decisionRecorded || !reason.trim()}
            className="rounded-xl border border-red-700 px-5 py-3 font-bold text-red-700 disabled:opacity-60">
            Reject vendor
          </button>
        </div>
        {decisionMessage && <p role="status" className="mt-4 text-sm">{decisionMessage}</p>}
      </section>}
    </main>
  );
}
