
import Link from "next/link";
import { SiteHeader } from "@/components/layout/site-header";
import { LoginForm } from "@/components/forms/login-form";
import { Container } from "@/components/ui/container";

export default function LoginPage() {
  return (
    <>
      <SiteHeader />

      <main className="min-h-screen bg-background px-4 py-12 sm:py-16">
        <Container size="narrow">
          <div className="mx-auto max-w-lg">
            <div className="mb-8 text-center">
              <h1 className="text-3xl font-bold tracking-tight text-text">
                Welcome back
              </h1>
              <p className="mt-3 text-sm leading-6 text-muted">
                Log in to continue buying or selling materials on ScrapMart.
              </p>
            </div>

            <LoginForm />

            <p className="mt-6 text-center text-sm text-muted">
              Don&apos;t have an account?{" "}
              <Link
                href="/onboarding"
                className="font-semibold text-primary hover:underline"
              >
                Get started
              </Link>
            </p>
          </div>
        </Container>
      </main>
    </>
  );
}