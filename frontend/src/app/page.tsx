import Image from "next/image";
import Link from "next/link";
import { SiteHeader } from "@/components/layout/site-header";
import { Container } from "@/components/ui/container";

const categories = [
  {
    name: "Plastics",
    description: "Bottles, containers and other plastic materials",
    image: "/images/category-plastics.jpg",
    href: "/marketplace?category=plastics",
  },
  {
    name: "Metals",
    description: "Scrap metal, aluminium, copper and more",
    image: "/images/category-metals.jpg",
    href: "/marketplace?category=metals",
  },
  {
    name: "Electronics",
    description: "Old appliances and electronic scrap",
    image: "/images/category-electronics.jpg",
    href: "/marketplace?category=electronics",
  },
];

export default function Home() {
  return (
    <>
      <div className="bg-[#064d31] px-4 py-2 text-center text-xs font-bold leading-4 text-white">
        PAY ON DELIVERY · Never pay before receiving your item
      </div>
      <SiteHeader variant="homepage" />

      <main>
        {/* Hero */}
        <section className="bg-[#f4f7f5] pb-16 pt-10 sm:pb-20 sm:pt-14 lg:pb-16 lg:pt-16">
          <div className="mx-auto w-full max-w-[1304px] px-4 sm:px-6 lg:px-8">
            <div className="grid items-center gap-12 lg:grid-cols-[minmax(0,1.088fr)_minmax(0,1fr)] lg:gap-[50px]">
              <div className="min-w-0">
                <p className="mb-6 inline-flex items-center gap-2 rounded-full bg-[#e8faf1] px-3 py-1.5 text-[13px] font-semibold text-[#006b52]">
                  <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-[#006b52]" />
                  Nigerian scrap marketplace
                </p>

                <h1 className="text-[42px] font-bold leading-[1.03] tracking-[-0.04em] text-[#15221b] sm:text-6xl lg:text-[clamp(48px,4.4vw,72px)]">
                  <span className="xl:whitespace-nowrap">Buy and sell scrap,</span>{" "}
                  <span className="text-[#087b40] lg:block">simply.</span>
                </h1>

                <p className="mt-6 max-w-[600px] text-base leading-[1.65] text-[#63736c] sm:text-lg">
                  Buy and sell reusable, used and scrap materials through a
                  Nigerian marketplace built for local trade. No advance payment
                  required.
                </p>

                <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
                  <Link
                    href="/onboarding"
                    className="inline-flex min-h-[50px] items-center justify-center gap-3 rounded-xl bg-[#087b40] px-8 py-3 text-sm font-medium text-white shadow-sm transition-colors hover:bg-[#066333] focus:outline-none focus:ring-2 focus:ring-[#087b40] focus:ring-offset-2"
                  >
                    Get started
                    <span aria-hidden="true">→</span>
                  </Link>
                  <Link
                    href="/login"
                    className="inline-flex min-h-[50px] items-center justify-center rounded-xl border border-[#dce4df] bg-white px-5 py-3 text-sm font-medium text-[#15221b] transition-colors hover:bg-[#edf5ef] focus:outline-none focus:ring-2 focus:ring-[#087b40] focus:ring-offset-2"
                  >
                    Log in to marketplace
                  </Link>
                </div>

                <div className="mt-8 flex flex-wrap gap-x-5 gap-y-3 text-sm font-semibold text-[#63736c]">
                  {[
                    "Browse scrap materials",
                    "Pay on delivery",
                    "Local marketplace",
                  ].map((label) => (
                    <span key={label} className="inline-flex items-center gap-2">
                      <span aria-hidden="true" className="font-normal text-[#087b40]">✓</span>
                      {label}
                    </span>
                  ))}
                </div>
              </div>

              <div className="relative min-w-0 pb-5 lg:ml-2">
                {/* Temporary still image; the approved video treatment is deferred. */}
                <div className="overflow-hidden rounded-[32px] bg-[#15221b] p-3 shadow-[0_28px_44px_-16px_rgba(21,34,27,0.38)]">
                  <Image
                    src="/images/hero-plastics.jpg"
                    alt="Plastic materials collected for recycling in Lagos"
                    width={1200}
                    height={900}
                    preload
                    className="h-[340px] w-full rounded-[22px] object-cover sm:h-[420px] lg:h-[440px] xl:h-[488px]"
                    sizes="(max-width: 1023px) 100vw, (max-width: 1304px) 44vw, 546px"
                  />
                </div>

                <div className="absolute bottom-0 left-3 w-[260px] max-w-[calc(100%-24px)] rounded-2xl border border-[#dce4df] bg-white p-4 shadow-[0_14px_26px_-8px_rgba(21,34,27,0.35)] sm:left-5 lg:-left-8 lg:p-5">
                  <p className="text-[11px] font-bold tracking-[0.12em] text-[#63736c]">
                    SAFE PAYMENT
                  </p>
                  <p className="mt-1 text-lg font-bold text-[#15221b]">
                    Pay only after delivery
                  </p>
                  <p className="mt-1 text-sm text-[#63736c]">
                    Cash, POS or transfer at delivery
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section aria-label="Marketplace reassurance" className="border-t border-[#dce4df] bg-white py-9">
          <div className="mx-auto grid w-full max-w-[1304px] gap-6 px-4 text-center sm:grid-cols-3 sm:px-6 lg:px-8">
            {[
              ["Browse materials", "Marketplace listings"],
              ["Connect locally", "Buyers and sellers"],
              ["Pay on delivery", "No advance payment"],
            ].map(([title, description]) => (
              <div key={title}>
                <p className="text-xl font-bold text-[#15221b] sm:text-2xl">{title}</p>
                <p className="mt-1 text-sm font-semibold text-[#63736c]">{description}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Categories */}
        <section className="bg-[#f4f7f5] py-16 sm:py-20">
          <Container className="max-w-[1304px]">
            <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
              <div>
                <p className="text-sm font-semibold uppercase tracking-wider text-[#438447]">
                  Explore materials
                </p>
                <h2 className="mt-2 text-3xl font-bold tracking-tight text-[#202820] sm:text-4xl">
                  What are you looking for?
                </h2>
                <p className="mt-3 max-w-2xl leading-7 text-[#687066]">
                  Browse popular categories and find materials that match your
                  needs.
                </p>
              </div>

              <Link
                href="/marketplace"
                className="inline-flex w-fit items-center gap-2 font-semibold text-[#347a3b] hover:text-[#286331]"
              >
                View marketplace <span aria-hidden="true">→</span>
              </Link>
            </div>

            <div className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {categories.map((category) => (
                <Link
                  key={category.name}
                  href={category.href}
                  className="group overflow-hidden rounded-2xl border border-[#dce4df] bg-white shadow-[0_8px_24px_-12px_rgba(21,34,27,0.16)] transition hover:-translate-y-1 hover:border-[#cbdcc5] hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-[#347a3b] focus:ring-offset-2"
                >
                  <div className="relative h-60 overflow-hidden bg-[#f1f3ee]">
                    <Image
                      src={category.image}
                      alt={`${category.name} scrap materials`}
                      fill
                      sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
                      className="object-cover transition duration-300 group-hover:scale-105"
                    />
                  </div>

                  <div className="p-5">
                    <div className="flex items-center justify-between gap-3">
                      <h3 className="text-xl font-bold text-[#263126]">
                        {category.name}
                      </h3>
                      <span
                        aria-hidden="true"
                        className="text-xl text-[#438447] transition group-hover:translate-x-1"
                      >
                        →
                      </span>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-[#687066]">
                      {category.description}
                    </p>
                  </div>
                </Link>
              ))}
            </div>
          </Container>
        </section>

        {/* Buyer and seller paths */}
        <section className="bg-[#f4f7f5] pb-16 sm:pb-20">
          <Container className="max-w-[1304px]">
            <div className="grid gap-6 md:grid-cols-2">
              <div className="rounded-3xl border border-[#dce4df] bg-[#e8f6ee] p-7 sm:p-9">
                <p className="text-sm font-semibold uppercase tracking-wider text-[#438447]">
                  For buyers
                </p>
                <h2 className="mt-3 text-2xl font-bold text-[#243224] sm:text-3xl">
                  Find materials. Connect with sellers.
                </h2>
                <p className="mt-3 leading-7 text-[#596558]">
                  Explore available listings, compare materials, and contact
                  vendors to discuss your purchase.
                </p>
                <Link
                  href="/marketplace"
                  className="mt-6 inline-flex items-center gap-2 font-semibold text-[#347a3b] hover:text-[#286331]"
                >
                  Browse materials <span aria-hidden="true">→</span>
                </Link>
              </div>

              <div className="rounded-3xl border border-[#e9e1ce] bg-[#faf6eb] p-7 sm:p-9">
                <p className="text-sm font-semibold uppercase tracking-wider text-[#80622c]">
                  For sellers
                </p>
                <h2 className="mt-3 text-2xl font-bold text-[#302b21] sm:text-3xl">
                  Give your scrap a new market.
                </h2>
                <p className="mt-3 leading-7 text-[#686153]">
                  Create listings for your materials and connect with people
                  looking to buy. Vendor verification helps build trust.
                </p>
                <Link
                  href="/onboarding?intent=sell"
                  className="mt-6 inline-flex items-center gap-2 font-semibold text-[#80622c] hover:text-[#634b20]"
                >
                  Start selling <span aria-hidden="true">→</span>
                </Link>
              </div>
            </div>
          </Container>
        </section>

        {/* Payment reassurance */}
        <section className="border-t border-[#e8ebe5] bg-white py-10">
          <Container className="max-w-[1304px]">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-lg font-bold text-[#263126]">
                  A straightforward way to trade
                </h2>
                <p className="mt-1 text-sm leading-6 text-[#687066]">
                  Agree on the materials and details with the vendor before
                  completing your transaction.
                </p>
              </div>
              <div className="flex items-center gap-3 rounded-lg border border-[#dce8d5] bg-[#f7faf4] px-4 py-3">
                <span
                  aria-hidden="true"
                  className="flex h-10 w-10 items-center justify-center rounded-full bg-[#e5efdf] text-lg text-[#347a3b]"
                >
                  ✓
                </span>
                <div>
                  <p className="font-semibold text-[#263126]">
                    Pay on delivery
                  </p>
                  <p className="text-sm text-[#687066]">
                    No advance payment required by ScrapMart
                  </p>
                </div>
              </div>
            </div>
          </Container>
        </section>
      </main>
    </>
  );
}
