
import Link from "next/link";

const navigationLinks = [
  { label: "Marketplace", href: "/" },
  { label: "Categories", href: "/categories" },
  { label: "How it works", href: "/how-it-works" },
];

type SiteHeaderProps = {
  variant?: "default" | "homepage" | "marketplace";
};

export function SiteHeader({ variant = "default" }: SiteHeaderProps) {
  if (variant === "marketplace") {
    return (
      <>
        <div className="bg-[#064d31] px-4 py-2 text-center text-xs font-bold leading-5 text-white">
          PAY ON DELIVERY · Never pay before receiving your item
        </div>
        <header className="border-b border-[#dce4df] bg-white">
          <div className="mx-auto flex w-full max-w-[1536px] flex-wrap items-center justify-between gap-x-6 gap-y-3 px-4 py-3 sm:px-6 lg:px-8">
            <Link href="/marketplace" className="inline-flex min-h-11 items-center gap-2 rounded-lg text-xl font-bold tracking-tight text-[#15221b] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#087b40]">
              <span aria-hidden="true" className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#087b40] text-white">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className="h-5 w-5"><path d="M4 10v10h16V10M3 10l2-6h14l2 6M8 20v-6h5v6M3 10c0 3 4 3 4 0 0 3 5 3 5 0 0 3 5 3 5 0 0 3 4 3 4 0" /></svg>
              </span>
              <span>Scrap<span className="text-[#087b40]">Mart</span></span>
            </Link>
            <nav aria-label="Marketplace navigation" className="flex flex-wrap items-center gap-1 text-sm text-[#63736c] sm:gap-2">
              {[
                { label: "Home", href: "/marketplace" },
                { label: "Categories", href: "/categories" },
                { label: "How it works", href: "/how-it-works" },
                { label: "Log in", href: "/login" },
                { label: "Get started", href: "/onboarding" },
              ].map((item) => (
                <Link key={item.href} href={item.href} aria-current={item.href === "/marketplace" ? "page" : undefined}
                  className={`inline-flex min-h-11 items-center rounded-lg px-3 transition-colors hover:bg-[#edf5ef] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#087b40] ${item.href === "/marketplace" ? "bg-[#e8f6ee] font-medium text-[#064d31]" : ""}`}>
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
      </>
    );
  }

  if (variant === "homepage") {
    return (
      <header className="bg-[#f4f7f5]">
        <div className="mx-auto flex w-full max-w-[1304px] flex-wrap items-center justify-between gap-4 px-4 py-5 sm:px-6 lg:px-8">
          <Link
            href="/marketplace"
            className="shrink-0 rounded-sm text-xl font-bold tracking-tight text-[#15221b] focus:outline-none focus:ring-2 focus:ring-[#087b40] focus:ring-offset-2"
          >
            Scrap<span className="text-[#087b40]">Mart</span>
          </Link>
          <Link
            href="/login"
            className="inline-flex min-h-[50px] items-center justify-center rounded-xl border border-[#dce4df] bg-white px-5 py-3 text-sm text-[#15221b] transition-colors hover:bg-[#edf5ef] focus:outline-none focus:ring-2 focus:ring-[#087b40] focus:ring-offset-2"
          >
            I already have an account
          </Link>
        </div>
      </header>
    );
  }

  return (
    <header className="border-b border-border bg-surface">
      <div className="mx-auto flex max-w-screen-2xl items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8">
        <Link
          href="/marketplace"
          className="shrink-0 text-2xl font-bold tracking-tight text-primary"
        >
          ScrapMart
        </Link>

        <nav
          aria-label="Main navigation"
          className="hidden items-center gap-6 md:flex"
        >
          {navigationLinks.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="text-sm font-medium text-text transition-colors hover:text-primary"
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="flex shrink-0 items-center gap-2">
          <Link
            href="/login"
            className="hidden rounded-md px-3 py-2 text-sm font-medium text-text hover:bg-background sm:inline-flex"
          >
            Log in
          </Link>

          <Link
            href="/onboarding"
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 font-medium text-white transition-colors hover:bg-primary-hover focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
          >
            Get started
          </Link>
        </div>
      </div>
    </header>
  );
}