
import Link from "next/link";
import { SiteHeader } from "@/components/layout/site-header";
import { SignupForm } from "@/components/forms/signup-form";
import { Badge } from "@/components/ui/badge";
import { Container } from "@/components/ui/container";

type SignupPageProps = {
  searchParams: Promise<{
    role?: string;
  }>;
};

export default async function SignupPage({
  searchParams,
}: SignupPageProps) {
  const params = await searchParams;
  const role = params.role === "vendor" ? "vendor" : "buyer";
  const isVendor = role === "vendor";

  return (
    <>
      <SiteHeader />

      <main className="min-h-screen bg-background px-4 py-12 sm:py-16">
        <Container size="narrow">
          <div className="mx-auto max-w-lg">
            <div className="mb-8 text-center">
              <Badge variant="success">
                {isVendor ? "Vendor registration" : "Buyer registration"}
              </Badge>

              <h1 className="mt-4 text-3xl font-bold tracking-tight text-text">
                {isVendor
                  ? "Create your vendor account"
                  : "Create your buyer account"}
              </h1>

              <p className="mt-3 text-sm leading-6 text-muted">
                {isVendor
                  ? "Register your business to list scrap materials and connect with buyers."
                  : "Create an account to discover materials and connect with vendors."}
              </p>
            </div>

            <SignupForm role={role} />

            <p className="mt-6 text-center text-sm text-muted">
              Already have an account?{" "}
              <Link
                href="/login"
                className="font-semibold text-primary hover:underline"
              >
                Log in
              </Link>
            </p>

            <p className="mt-4 text-center text-sm text-muted">
              {isVendor
                ? "Want to buy materials instead?"
                : "Want to sell scrap materials instead?"}{" "}
              <Link
                href={`/signup?role=${isVendor ? "buyer" : "vendor"}`}
                className="font-semibold text-primary hover:underline"
              >
                Switch registration type
              </Link>
            </p>
          </div>
        </Container>
      </main>
    </>
  );
}