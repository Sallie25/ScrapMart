
import { SiteHeader } from "@/components/layout/site-header";
import { ListingCard } from "@/components/marketplace/listing-card";
import { Container } from "@/components/ui/container";
import { PageHeader } from "@/components/ui/page-header";
import { demoListings } from "@/lib/data/listings";

export default function MarketplacePage() {
  return (
    <>
      <SiteHeader />

      <main className="min-h-screen bg-background py-10 sm:py-14">
        <Container>
          <PageHeader
            title="Discover scrap materials"
            description="Explore materials listed by vendors across Lagos."
          />

          <section className="mt-8">
            <div className="mb-5 flex items-center justify-between gap-4">
              <h2 className="text-lg font-semibold text-text">
                Recently listed
              </h2>
              <p className="text-sm text-muted">
                {demoListings.length} listings
              </p>
            </div>

            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {demoListings.map((listing) => (
                <ListingCard key={listing.id} listing={listing} />
              ))}
            </div>
          </section>
        </Container>
      </main>
    </>
  );
}