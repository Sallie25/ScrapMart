
import Link from "next/link";
import { SiteHeader } from "@/components/layout/site-header";
import { Container } from "@/components/ui/container";

export default function Home() {
  return (
    <>
      <SiteHeader />

      <main className="py-16 sm:py-24">
        <Container>
          <div className="mx-auto max-w-3xl text-center">
            <p className="mb-4 text-sm font-semibold uppercase tracking-wider text-primary">
              Your marketplace for scrap materials
            </p>

            <h1 className="text-4xl font-bold tracking-tight text-text sm:text-5xl">
              Turn unwanted materials into valuable opportunities.
            </h1>

            <p className="mx-auto mt-6 max-w-2xl text-base leading-7 text-muted sm:text-lg">
              Discover scrap materials, connect with vendors, and find buyers
              for materials you no longer need.
            </p>

            <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
              <Link
                href="/onboarding?intent=buy"
                className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 font-medium text-white transition-colors hover:bg-primary-hover focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
              >
                Browse materials
              </Link>

              <Link
                href="/onboarding?intent=sell"
                className="inline-flex items-center justify-center rounded-md border border-border bg-surface px-4 py-2 font-medium text-text transition-colors hover:bg-background focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
              >
                Start selling
              </Link>
            </div>
          </div>
        </Container>
      </main>
    </>
  );
}