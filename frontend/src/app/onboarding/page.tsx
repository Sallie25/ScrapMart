
import Link from "next/link";
import { SiteHeader } from "@/components/layout/site-header";
import { Card } from "@/components/ui/card";
import { Container } from "@/components/ui/container";
import { Badge } from "@/components/ui/badge";

type OnboardingPageProps = {
  searchParams: Promise<{
    intent?: string;
  }>;
};

export default async function OnboardingPage({
  searchParams,
}: OnboardingPageProps) {
  const params = await searchParams;
  const intent = params.intent;

  const selectedIntent =
    intent === "buy" || intent === "sell" ? intent : null;

  return (
    <>
      <SiteHeader />

      <main className="min-h-screen bg-background py-12 sm:py-20">
        <Container size="narrow">
          <div className="mb-10 text-center">
            <Badge variant="success">Welcome to ScrapMart</Badge>

            <h1 className="mt-5 text-3xl font-bold tracking-tight text-text sm:text-4xl">
              What would you like to do?
            </h1>

            <p className="mt-4 text-base leading-7 text-muted">
              Choose how you want to use ScrapMart. You can get started
              with the journey that suits you.
            </p>
          </div>

          <div className="grid gap-5 sm:grid-cols-2">
            <Card
              className={`flex flex-col ${
                selectedIntent === "buy"
                  ? "border-2 border-primary"
                  : ""
              }`}
            >
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-green-100 text-2xl">
                🛒
              </div>

              <h2 className="text-xl font-bold text-text">
                I want to buy
              </h2>

              <p className="mt-3 flex-1 text-sm leading-6 text-muted">
                Discover scrap materials, compare listings, find vendors,
                and arrange delivery with payment on delivery.
              </p>

              {selectedIntent === "buy" && (
                <p className="mt-3">
                  <Badge variant="success">Your selection</Badge>
                </p>
              )}

              <Link
                href="/signup?role=buyer"
                className="mt-6 inline-flex w-full items-center justify-center rounded-md bg-primary px-4 py-3 font-medium text-white transition-colors hover:bg-primary-hover focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
              >
                Continue as a buyer
              </Link>
            </Card>

            <Card
              className={`flex flex-col ${
                selectedIntent === "sell"
                  ? "border-2 border-primary"
                  : ""
              }`}
            >
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-green-100 text-2xl">
                ♻️
              </div>

              <h2 className="text-xl font-bold text-text">
                I want to sell
              </h2>

              <p className="mt-3 flex-1 text-sm leading-6 text-muted">
                Create a vendor account, complete identity verification,
                publish your scrap listings, and manage orders.
              </p>

              {selectedIntent === "sell" && (
                <p className="mt-3">
                  <Badge variant="success">Your selection</Badge>
                </p>
              )}

              <Link
                href="/signup?role=vendor"
                className="mt-6 inline-flex w-full items-center justify-center rounded-md border border-border bg-surface px-4 py-3 font-medium text-text transition-colors hover:bg-background focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
              >
                Continue as a vendor
              </Link>
            </Card>
          </div>

          <p className="mt-8 text-center text-sm text-muted">
            Already have an account?{" "}
            <Link
              href="/login"
              className="font-semibold text-primary underline-offset-4 hover:underline"
            >
              Log in
            </Link>
          </p>
        </Container>
      </main>
    </>
  );
}