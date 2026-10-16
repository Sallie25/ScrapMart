
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
      <SiteHeader />

      <main>
        {/* Hero */}
        <section className="overflow-hidden bg-[#f7f8f3] py-14 sm:py-20 lg:py-24">
          <Container>
            <div className="grid items-center gap-12 lg:grid-cols-2 lg:gap-16">
              <div>
                <p className="mb-5 inline-flex items-center gap-2 rounded-full border border-[#dce8d5] bg-white px-4 py-2 text-sm font-semibold text-[#356b38]">
                  <span className="h-2 w-2 rounded-full bg-[#4b914e]" />
                  A better way to buy and sell scrap
                </p>

                <h1 className="max-w-xl text-4xl font-bold leading-tight tracking-tight text-[#202820] sm:text-5xl lg:text-6xl">
                  Good materials deserve a{" "}
                  <span className="text-[#438447]">second market.</span>
                </h1>

                <p className="mt-6 max-w-xl text-base leading-8 text-[#5e675d] sm:text-lg">
                  Turn unwanted materials into new opportunities. Discover
                  scrap near you, connect with vendors, and give useful
                  materials another life.
                </p>

                <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                  <Link
                    href="/marketplace"
                    className="inline-flex min-h-12 items-center justify-center rounded-lg bg-[#347a3b] px-6 py-3 font-semibold text-white transition hover:bg-[#286331] focus:outline-none focus:ring-2 focus:ring-[#347a3b] focus:ring-offset-2"
                  >
                    Explore marketplace
                    <span aria-hidden="true" className="ml-2">
                      →
                    </span>
                  </Link>

                  <Link
                    href="/onboarding?intent=sell"
                    className="inline-flex min-h-12 items-center justify-center rounded-lg border border-[#d5ddd1] bg-white px-6 py-3 font-semibold text-[#273b29] transition hover:bg-[#f0f4ed] focus:outline-none focus:ring-2 focus:ring-[#347a3b] focus:ring-offset-2"
                  >
                    Start selling
                  </Link>
                </div>

                <div className="mt-8 flex flex-wrap gap-x-6 gap-y-3 text-sm text-[#596558]">
                  <span className="inline-flex items-center gap-2">
                    <span className="font-bold text-[#347a3b]">✓</span>
                    Vendor verification
                  </span>
                  <span className="inline-flex items-center gap-2">
                    <span className="font-bold text-[#347a3b]">✓</span>
                    Pay on delivery
                  </span>
                  <span className="inline-flex items-center gap-2">
                    <span className="font-bold text-[#347a3b]">✓</span>
                    Connect with vendors
                  </span>
                </div>
              </div>

              <div className="relative">
                <div className="absolute -inset-4 rounded-[2rem] bg-[#e5eddf]" />

                <div className="relative overflow-hidden rounded-2xl bg-white shadow-xl">
                  <Image
                    src="/images/hero-plastics.jpg"
                    alt="Plastic materials collected for recycling in Lagos"
                    width={1200}
                    height={900}
                    priority
                    className="h-[320px] w-full object-cover sm:h-[420px] lg:h-[480px]"
                    sizes="(max-width: 1024px) 100vw, 50vw"
                  />

                  <div className="absolute inset-x-4 bottom-4 rounded-xl border border-white/60 bg-white/95 p-4 shadow-lg backdrop-blur-sm sm:inset-x-5 sm:bottom-5 sm:p-5">
                    <p className="text-sm font-semibold text-[#347a3b]">
                      Waste less. Find value.
                    </p>
                    <p className="mt-1 text-sm leading-6 text-[#515b50]">
                      Connect with people who buy and sell reusable and scrap
                      materials.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </Container>
        </section>

        {/* Categories */}
        <section className="py-16 sm:py-20">
          <Container>
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
                  className="group overflow-hidden rounded-2xl border border-[#e6e9e2] bg-white transition hover:-translate-y-1 hover:border-[#cbdcc5] hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-[#347a3b] focus:ring-offset-2"
                >
                  <div className="relative h-52 overflow-hidden bg-[#f1f3ee]">
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
        <section className="pb-16 sm:pb-20">
          <Container>
            <div className="grid gap-6 md:grid-cols-2">
              <div className="rounded-2xl bg-[#edf4e9] p-7 sm:p-9">
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

              <div className="rounded-2xl bg-[#f5f2e9] p-7 sm:p-9">
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
          <Container>
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
