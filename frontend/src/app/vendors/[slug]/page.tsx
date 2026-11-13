import Link from "next/link";
import { SiteHeader } from "@/components/layout/site-header";
import { Container } from "@/components/ui/container";

export default function VendorProfilePage() {
  return <><SiteHeader /><main className="min-h-screen bg-background py-8 sm:py-12"><Container>
    <section role="status" className="rounded-2xl border border-border bg-white p-6 sm:p-8">
      <h1 className="text-2xl font-bold text-text">Vendor profile unavailable</h1>
      <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">Public Vendor profiles are not provided by the current marketplace API. Each live listing shows its approved Vendor and public location.</p>
      <Link href="/marketplace" className="mt-5 inline-block rounded-lg bg-primary px-4 py-3 text-sm font-semibold text-white">Browse live listings</Link>
    </section>
  </Container></main></>;
}
