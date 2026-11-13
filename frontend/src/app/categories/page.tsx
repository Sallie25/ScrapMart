import Link from "next/link";
import { SiteHeader } from "@/components/layout/site-header";
import { Container } from "@/components/ui/container";
import { PageHeader } from "@/components/ui/page-header";
import { marketplaceClient } from "@/lib/server/marketplace/client";

export const dynamic = "force-dynamic";

export default async function CategoriesPage() {
  let categories: Awaited<ReturnType<ReturnType<typeof marketplaceClient>["categories"]>> = [];
  let unavailable = false;
  try { categories = await marketplaceClient().categories(); }
  catch { unavailable = true; }
  return <>
    <SiteHeader />
    <main className="min-h-screen bg-background py-10 sm:py-14">
      <Container>
        <PageHeader title="Browse by category" description="Explore available scrap materials by category." />
        {unavailable ? <section role="alert" className="mt-8 rounded-2xl border border-border bg-white p-6">Categories are temporarily unavailable. Please try again.</section> :
          categories.length === 0 ? <p className="mt-8 text-muted">No categories are available yet.</p> :
          <div className="mt-8 grid grid-cols-1 gap-5 sm:grid-cols-2">
            {categories.map(category => <article key={category.id} className="rounded-2xl border border-border bg-white p-6">
              <h2 className="text-xl font-bold text-text">{category.name}</h2>
              <Link href={`/marketplace?category_id=${encodeURIComponent(category.id)}`} className="mt-5 inline-block font-semibold text-primary hover:underline">Browse listings →</Link>
            </article>)}
          </div>}
      </Container>
    </main>
  </>;
}
