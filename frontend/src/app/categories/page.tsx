
import Link from "next/link";
import { SiteHeader } from "@/components/layout/site-header";
import { Container } from "@/components/ui/container";
import { PageHeader } from "@/components/ui/page-header";

const categories = [
  {
    name: "Metals",
    emoji: "🔩",
    description: "Aluminium, copper, iron, steel, and metal offcuts.",
  },
  {
    name: "Plastics",
    emoji: "♻️",
    description: "Used plastic bottles and other recyclable plastics.",
  },
  {
    name: "Paper",
    emoji: "📦",
    description: "Cardboard, paper bundles, and recyclable packaging.",
  },
  {
    name: "Electronics",
    emoji: "🔌",
    description: "Faulty electrical equipment and electronic scrap.",
  },
];

export default function CategoriesPage() {
  return (
    <>
      <SiteHeader />
      <main className="min-h-screen bg-background py-10 sm:py-14">
        <Container>
          <PageHeader
            title="Browse by category"
            description="Explore scrap materials by the type of material you need."
          />

          <div className="mt-8 grid grid-cols-1 gap-5 sm:grid-cols-2">
            {categories.map((category) => (
              <article
                key={category.name}
                className="rounded-2xl border border-border bg-white p-6"
              >
                <span className="text-4xl" aria-hidden="true">
                  {category.emoji}
                </span>
                <h2 className="mt-4 text-xl font-bold text-text">
                  {category.name}
                </h2>
                <p className="mt-2 leading-6 text-muted">
                  {category.description}
                </p>
                <Link
                  href={`/marketplace?category=${encodeURIComponent(category.name)}`}
                  className="mt-5 inline-flex rounded-lg bg-primary px-4 py-3 text-sm font-semibold text-white hover:opacity-90"
                >
                  Browse materials
                </Link>
              </article>
            ))}
          </div>

          <div className="mt-8 rounded-xl border border-border bg-white p-6">
            <h2 className="text-lg font-bold text-text">
              Looking for something specific?
            </h2>
            <p className="mt-2 text-muted">
              Search by material, vendor, or location in the marketplace.
            </p>
            <Link
              href="/marketplace"
              className="mt-4 inline-block font-semibold text-primary hover:underline"
            >
              Open marketplace →
            </Link>
          </div>
        </Container>
      </main>
    </>
  );
}
