
import Link from "next/link";
import { SiteHeader } from "@/components/layout/site-header";
import { Container } from "@/components/ui/container";
import { PageHeader } from "@/components/ui/page-header";

const buyerSteps = [
  {
    number: "01",
    title: "Discover materials",
    description:
      "Browse scrap listings and use search and filters to find suitable materials.",
  },
  {
    number: "02",
    title: "Review the listing",
    description:
      "Check the material description, condition, price, available quantity, and location.",
  },
  {
    number: "03",
    title: "Contact the vendor",
    description:
      "Use the listing contact form to start the conversation. In this prototype, messages are not sent to a server.",
  },
  {
    number: "04",
    title: "Inspect and pay on delivery",
    description:
      "Agree on collection details, inspect the material, and use the Pay on Delivery arrangement.",
  },
];

const vendorSteps = [
  {
    number: "01",
    title: "Choose to sell",
    description:
      "Start onboarding as a vendor and provide your account and shop details.",
  },
  {
    number: "02",
    title: "Create a listing",
    description:
      "Add the material name, category, condition, price, quantity, and location.",
  },
  {
    number: "03",
    title: "Manage your listings",
    description:
      "Review your demo listings from the vendor dashboard.",
  },
  {
    number: "04",
    title: "Arrange the transaction",
    description:
      "Discuss collection with the buyer and follow the Pay on Delivery policy.",
  },
];

export default function HowItWorksPage() {
  return (
    <>
      <SiteHeader />
      <main className="min-h-screen bg-background py-10 sm:py-14">
        <Container>
          <PageHeader
            title="How ScrapMart works"
            description="A marketplace prototype for discovering and listing scrap materials."
          />

          <section className="mt-10">
            <h2 className="text-2xl font-bold text-text">For buyers</h2>
            <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
              {buyerSteps.map((step) => (
                <article
                  key={step.number}
                  className="rounded-xl border border-border bg-white p-6"
                >
                  <p className="text-sm font-bold text-primary">
                    STEP {step.number}
                  </p>
                  <h3 className="mt-2 text-lg font-bold text-text">
                    {step.title}
                  </h3>
                  <p className="mt-2 leading-6 text-muted">
                    {step.description}
                  </p>
                </article>
              ))}
            </div>
            <Link
              href="/marketplace"
              className="mt-5 inline-flex rounded-lg bg-primary px-5 py-3 font-semibold text-white hover:opacity-90"
            >
              Explore marketplace
            </Link>
          </section>

          <section className="mt-12">
            <h2 className="text-2xl font-bold text-text">For vendors</h2>
            <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
              {vendorSteps.map((step) => (
                <article
                  key={step.number}
                  className="rounded-xl border border-border bg-white p-6"
                >
                  <p className="text-sm font-bold text-primary">
                    STEP {step.number}
                  </p>
                  <h3 className="mt-2 text-lg font-bold text-text">
                    {step.title}
                  </h3>
                  <p className="mt-2 leading-6 text-muted">
                    {step.description}
                  </p>
                </article>
              ))}
            </div>
            <Link
              href="/onboarding?intent=sell"
              className="mt-5 inline-flex rounded-lg bg-primary px-5 py-3 font-semibold text-white hover:opacity-90"
            >
              Start selling
            </Link>
          </section>

          <aside className="mt-12 rounded-xl border border-border bg-white p-6">
            <h2 className="text-lg font-bold text-text">
              Prototype transparency
            </h2>
            <p className="mt-2 leading-6 text-muted">
              This version uses browser-local demo listings. Account creation,
              identity verification, server messaging, and real transactions
              are not connected yet. Pay on Delivery is the intended payment
              policy; do not send advance payments.
            </p>
          </aside>
        </Container>
      </main>
    </>
  );
}
