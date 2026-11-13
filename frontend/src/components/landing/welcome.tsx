"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";

type Role = "buyer" | "vendor";

function Icon({
  name,
  className = "size-5",
}: {
  name: string;
  className?: string;
}) {
  const paths: Record<string, React.ReactNode> = {
    bag: (
      <>
        <path d="M5 8h14l-1 12H6L5 8Z" />
        <path d="M9 9V6a3 3 0 0 1 6 0v3" />
      </>
    ),
    store: (
      <>
        <path d="M4 10v10h16V10M3 10l2-6h14l2 6" />
        <path d="M3 10c1 3 4 3 5 0 1 3 4 3 5 0 1 3 4 3 5 0 1 3 4 3 5 0M9 20v-5h6v5" />
      </>
    ),
    pin: (
      <>
        <path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z" />
        <circle cx="12" cy="10" r="2" />
      </>
    ),
    plus: <path d="M12 5v14M5 12h14" />,
    check: <path d="m5 12 4 4L19 6" />,
    document: (
      <>
        <path d="M6 3h8l4 4v14H6z" />
        <path d="M14 3v5h5M9 13h6M9 17h5" />
      </>
    ),
    instagram: (
      <>
        <rect x="3" y="3" width="18" height="18" rx="5" />
        <circle cx="12" cy="12" r="4" />
        <path d="M17.5 6.5h.01" />
      </>
    ),
    facebook: (
      <path d="M14 21v-8h3l.5-4H14V7c0-1.2.5-2 2.2-2H18V1.5c-.8-.1-1.8-.2-2.8-.2C12.3 1.3 10 3.1 10 6.5V9H7v4h3v8" />
    ),
    whatsapp: (
      <>
        <path d="M20 11.5a8 8 0 0 1-11.8 7L4 20l1.4-4A8 8 0 1 1 20 11.5Z" />
        <path d="M9 8c.5 3 2 4.5 5 5l1-1 2 1.2c-.3 1.5-1.3 2.3-2.8 2.3-3.8 0-7.7-3.8-7.7-7.6C6.5 6.5 7.3 5.5 8.8 5L10 7 9 8Z" />
      </>
    ),
    x: (
      <>
        <path d="m5 4 14 16M19 4 5 20" />
      </>
    ),
    metal: (
      <>
        <path d="M4 8h16l-2 10H6L4 8Z" />
        <path d="M8 8V5h8v3M9 12h6" />
      </>
    ),
    plastic: (
      <>
        <path d="M9 3h6v4l2 3v10H7V10l2-3V3Z" />
        <path d="M9 7h6M10 13h4" />
      </>
    ),
    glass: (
      <>
        <path d="M7 3h10l-1 9a4 4 0 0 1-8 0L7 3Z" />
        <path d="M12 16v5M9 21h6" />
      </>
    ),
    electronics: (
      <>
        <rect x="4" y="5" width="16" height="12" rx="2" />
        <path d="M9 21h6M12 17v4M8 9h3v4H8zM14 9h2M14 12h2" />
      </>
    ),
    auto: (
      <>
        <path d="m5 11 2-5h10l2 5" />
        <path d="M3 11h18v7H3zM6 18v2M18 18v2" />
        <circle cx="7" cy="14.5" r="1" />
        <circle cx="17" cy="14.5" r="1" />
      </>
    ),
    menu: <path d="M4 7h16M4 12h16M4 17h16" />,
    close: <path d="m6 6 12 12M18 6 6 18" />,
  };
  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name]}
    </svg>
  );
}

function Button({
  children,
  href,
  onClick,
  variant = "primary",
  className = "",
  type = "button",
  disabled = false,
}: React.PropsWithChildren<{
  href?: string;
  onClick?: () => void;
  variant?: "primary" | "ghost" | "light" | "outlineLight";
  className?: string;
  type?: "button" | "submit";
  disabled?: boolean;
}>) {
  const styles = {
    primary:
      "bg-[var(--landing-brand)] text-white hover:bg-[var(--landing-brand-dark)] shadow-sm",
    ghost:
      "bg-white text-[var(--landing-ink)] border border-[var(--landing-line)] hover:border-[var(--landing-brand)]/40 hover:bg-[var(--landing-canvas)]",
    light:
      "bg-white text-[var(--landing-brand-dark)] hover:bg-[var(--landing-brand-soft)] shadow-sm",
    outlineLight:
      "border border-white/50 bg-transparent text-white hover:bg-white hover:text-[var(--landing-brand-dark)]",
  };
  const classes = `inline-flex min-h-10 items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-bold tracking-tight transition duration-200 hover:-translate-y-px ${styles[variant]} ${className}`;
  return href ? (
    <Link href={href} className={classes}>
      {children}
    </Link>
  ) : (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      className={classes}
    >
      {children}
    </button>
  );
}
function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2 text-left">
      <span className="grid size-9 place-items-center rounded-xl bg-[var(--landing-brand)] text-white">
        <Icon name="store" className="size-5" />
      </span>
      <span className="[font-family:var(--font-landing-manrope)] text-xl font-extrabold tracking-tight text-[var(--landing-ink)]">
        Scrap<span className="text-[var(--landing-brand)]">Mart</span>
      </span>
    </Link>
  );
}

function Badge({
  children,
  tone = "green",
}: React.PropsWithChildren<{
  tone?: "green" | "amber" | "orange" | "red" | "gray";
}>) {
  const tones = {
    green: "bg-emerald-50 text-emerald-800",
    amber: "bg-amber-50 text-amber-800",
    orange: "bg-orange-50 text-orange-800",
    red: "bg-red-50 text-red-800",
    gray: "bg-slate-100 text-slate-700",
  };
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-bold ${tones[tone]}`}
    >
      <span className="size-1.5 rounded-full bg-current" />
      {children}
    </span>
  );
}

function LandingHeader() {
  const [open, setOpen] = useState(false);
  return (
    <header className="sticky top-0 z-40 border-b border-[var(--landing-line)]/70 bg-[var(--landing-canvas)]/90 shadow-[0_4px_20px_rgba(16,42,28,0.04)] backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-5 py-4">
        <Logo />
        <div className="flex items-center gap-2">
          <details className="relative hidden sm:block">
            <summary className="cursor-pointer rounded-xl border border-[var(--landing-line)] bg-white px-3 py-2.5 text-sm font-bold">
              Explore
            </summary>
            <nav
              aria-label="Existing ScrapMart pages"
              className="absolute right-0 mt-2 grid w-48 gap-1 rounded-xl border border-[var(--landing-line)] bg-white p-3 shadow-xl"
            >
              {[
                ["Marketplace", "/marketplace"],
                ["Categories", "/categories"],
                ["How it works", "/how-it-works"],
                ["Get started", "/onboarding"],
              ].map(([label, href]) => (
                <Link
                  key={href}
                  href={href}
                  className="rounded-lg px-3 py-2 text-sm hover:bg-[var(--landing-brand-soft)]"
                >
                  {label}
                </Link>
              ))}
            </nav>
          </details>
          <div className="hidden sm:block">
            <Button href="/login" variant="ghost">
              I already have an account
            </Button>
          </div>
          <button
            type="button"
            onClick={() => setOpen(!open)}
            aria-expanded={open}
            aria-controls="landing-mobile-nav"
            aria-label={open ? "Close navigation" : "Open navigation"}
            className="grid size-10 place-items-center rounded-xl border border-[var(--landing-line)] bg-white sm:hidden"
          >
            <Icon name={open ? "close" : "menu"} />
          </button>
        </div>
        {open && (
          <nav
            id="landing-mobile-nav"
            aria-label="Mobile navigation"
            className="grid w-full gap-1 border-t border-[var(--landing-line)] pt-3 sm:hidden"
          >
            {[
              ["Marketplace", "/marketplace"],
              ["Categories", "/categories"],
              ["How it works", "/how-it-works"],
              ["Get started", "/onboarding"],
              ["I already have an account", "/login"],
            ].map(([label, href]) => (
              <Link
                onClick={() => setOpen(false)}
                key={href}
                href={href}
                className="rounded-xl px-3 py-3 text-sm font-bold hover:bg-[var(--landing-brand-soft)]"
              >
                {label}
              </Link>
            ))}
          </nav>
        )}
      </div>
    </header>
  );
}
function OnboardingFooter() {
  const columns = [
    [
      "For buyers",
      [
        ["How buying works", "/how-it-works"],
        ["Browse materials", "/marketplace"],
        ["Buyer FAQ", "#faq"],
      ],
    ],
    [
      "For vendors",
      [
        ["How to sell", "/how-it-works"],
        ["Become a verified vendor", "/signup?role=vendor"],
        ["Vendor guidelines", "/how-it-works"],
      ],
    ],
    [
      "Support",
      [
        ["Help center", "#faq"],
        ["Contact us", "#demo-contact"],
        ["Report a problem", "#demo-contact"],
      ],
    ],
    [
      "Legal",
      [
        ["Terms of Service", "#demo-legal"],
        ["Privacy Policy", "#demo-legal"],
        ["Prohibited items", "#faq"],
      ],
    ],
  ] as const;
  return (
    <footer className="px-4 pb-4 pt-10 sm:px-5 sm:pb-5">
      <div className="mx-auto max-w-7xl overflow-hidden rounded-3xl bg-[var(--landing-brand-dark)] text-white shadow-[0_8px_30px_rgba(16,42,28,0.07)]">
        <div className="grid gap-9 px-6 py-10 sm:grid-cols-2 sm:px-8 lg:grid-cols-[1.35fr_repeat(4,1fr)_1.25fr] lg:gap-7 lg:px-10 lg:py-12">
          <div>
            <Link href="/" className="flex items-center gap-2 text-left">
              <span className="grid size-9 place-items-center rounded-xl bg-white text-[var(--landing-brand-dark)]">
                <Icon name="store" />
              </span>
              <span className="[font-family:var(--font-landing-manrope)] text-xl font-extrabold">
                Scrap
                <span className="text-[var(--landing-brand-light)]">Mart</span>
              </span>
            </Link>
            <p className="mt-4 max-w-52 text-sm font-medium leading-relaxed text-slate-200">
              Nigeria&apos;s trusted scrap marketplace
            </p>
            <div className="mt-5 flex gap-2.5">
              {[
                ["Instagram", "instagram"],
                ["X", "x"],
                ["Facebook", "facebook"],
                ["WhatsApp", "whatsapp"],
              ].map(([label, icon]) => (
                <a
                  key={label}
                  href="#demo-contact"
                  aria-label={`${label} — demo contact details`}
                  className="grid size-9 place-items-center rounded-full bg-white/10 text-[var(--landing-brand-light)] ring-1 ring-white/10 transition hover:bg-white hover:text-[var(--landing-brand-dark)]"
                >
                  <Icon name={icon} className="size-[17px]" />
                </a>
              ))}
            </div>
          </div>
          {columns.map(([heading, links]) => (
            <div key={heading}>
              <p className="text-sm font-extrabold text-white">{heading}</p>
              <div className="mt-4 grid gap-3">
                {links.map(([label, href]) => (
                  <Link
                    key={label}
                    href={href}
                    className="w-fit text-left text-sm font-medium leading-relaxed text-[var(--landing-brand-light)] transition hover:text-white"
                  >
                    {label}
                  </Link>
                ))}
              </div>
            </div>
          ))}
          <div id="demo-contact">
            <p className="text-sm font-extrabold text-white">Contact</p>
            <div className="mt-4 grid gap-3 text-sm font-medium text-[var(--landing-brand-light)]">
              <span>+234 801 234 5678</span>
              <span>WhatsApp support</span>
              <span className="break-all">support@scrapmart.ng</span>
            </div>
            <p className="mt-3 text-xs leading-relaxed text-slate-200">
              Sample contact details. Support channels are not connected in this
              prototype.
            </p>
          </div>
        </div>
        <div
          id="demo-legal"
          className="border-t border-white/10 px-6 py-5 text-center text-sm font-medium text-slate-300"
        >
          <p className="mb-2 text-xs">
            Presentation prototype · Account creation, vendor verification,
            messaging and transactions are not connected. Terms and Privacy
            pages are not available yet.
          </p>
          © 2026 ScrapMart. All rights reserved.
        </div>
      </div>
    </footer>
  );
}
function OnboardingSections() {
  const [audience, setAudience] = useState<Role>("buyer");
  const [openFaq, setOpenFaq] = useState<number | null>(0);
  const materials = [
    ["Metal", "metal"],
    ["Plastic", "plastic"],
    ["Paper", "document"],
    ["Glass", "glass"],
    ["E-waste", "electronics"],
    ["Auto parts", "auto"],
  ];
  const steps =
    audience === "buyer"
      ? [
          [
            "Browse listings",
            "Explore materials and used items in the demo marketplace.",
          ],
          [
            "Agree a price with the vendor",
            "Chat directly and confirm the item and delivery details.",
          ],
          [
            "Pay only after delivery",
            "Inspect your item first, then pay when it arrives.",
          ],
        ]
      : [
          [
            "Create a free listing",
            "Add clear photos, a price and simple item details.",
          ],
          [
            "Get matched with local buyers",
            "Reach interested buyers in your area.",
          ],
          [
            "Get paid on pickup",
            "Receive payment when the buyer collects the item.",
          ],
        ];
  const benefits = [
    [
      "Verified vendors",
      "check",
      "Vendor review is part of our planned verification process.",
    ],
    ["Pay on delivery", "bag", "Your money stays with you until delivery."],
    [
      "Local sellers near you",
      "pin",
      "Find materials available around your city.",
    ],
  ];
  const faqs = [
    [
      "Is ScrapMart free?",
      "Yes. Buyers can browse for free, and vendors can create standard listings without an upfront fee.",
    ],
    [
      "How does pay on delivery work?",
      "You agree on delivery with the vendor, inspect the item when it arrives, and only then complete payment.",
    ],
    [
      "How are vendors verified?",
      "The planned process reviews identity, phone and shop information before a vendor receives a verified badge. Verification is not connected in this prototype.",
    ],
    [
      "What if the item isn't as described?",
      "Do not pay for or accept the item. Reporting and support are planned features and are not connected in this prototype.",
    ],
    [
      "Which materials are not allowed?",
      "Hazardous waste, stolen goods, weapons, illegal materials and other prohibited items cannot be listed.",
    ],
  ];
  return (
    <div>
      <section className="mx-auto max-w-7xl px-5 py-20 lg:py-24">
        <div className="max-w-2xl">
          <p className="landing-eyebrow">Browse by material</p>
          <h2 className="landing-section-title">What are you looking for?</h2>
          <p className="mt-3 text-base font-medium text-[var(--landing-muted)]">
            Explore popular scrap and reusable material categories.
          </p>
        </div>
        <div className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {materials.map(([label, icon]) => (
            <Link
              key={label}
              href="/signup?role=buyer"
              className="group flex min-h-32 flex-col items-center justify-center gap-4 rounded-2xl border border-[var(--landing-line)] bg-white p-5 text-center shadow-[0_5px_20px_rgba(16,42,28,0.035)] transition-all duration-200 hover:-translate-y-1 hover:border-[var(--landing-brand)]/30 hover:shadow-[0_8px_30px_rgba(16,42,28,0.07)]"
            >
              <span className="grid size-11 place-items-center rounded-xl bg-[var(--landing-brand-soft)] text-[var(--landing-brand)] transition group-hover:bg-[var(--landing-brand)] group-hover:text-white">
                <Icon name={icon} />
              </span>
              <span className="text-sm font-extrabold text-[var(--landing-ink)]">
                {label}
              </span>
            </Link>
          ))}
        </div>
      </section>
      <section className="border-y border-[var(--landing-line)] bg-white px-5 py-20 lg:py-24">
        <div className="mx-auto max-w-7xl">
          <div className="mx-auto max-w-2xl text-center">
            <p className="landing-eyebrow">Simple from start to finish</p>
            <h2 className="landing-section-title">How ScrapMart works</h2>
            <p className="mt-3 text-base font-medium text-[var(--landing-muted)]">
              Three clear steps. No complicated process.
            </p>
          </div>
          <div
            aria-label="How ScrapMart works audience"
            className="mx-auto mt-8 flex w-fit rounded-2xl bg-[var(--landing-canvas)] p-1.5"
          >
            {(
              [
                ["For buyers", "buyer"],
                ["For sellers", "vendor"],
              ] as const
            ).map(([label, value]) => (
              <button
                key={value}
                aria-pressed={audience === value}
                aria-controls="landing-steps"
                onClick={() => setAudience(value)}
                className={`min-w-32 rounded-xl px-5 py-2.5 text-sm font-extrabold transition ${audience === value ? "bg-[var(--landing-brand)] text-white shadow-sm" : "text-[var(--landing-muted)] hover:text-[var(--landing-ink)]"}`}
              >
                {label}
              </button>
            ))}
          </div>
          <div
            id="landing-steps"
            aria-live="polite"
            className="mt-9 grid gap-4 md:grid-cols-3"
          >
            {steps.map(([title, description], index) => (
              <article
                key={title}
                className="rounded-2xl border border-[var(--landing-line)] bg-[var(--landing-canvas)]/60 p-6"
              >
                <span className="grid size-9 place-items-center rounded-full bg-[var(--landing-brand)] text-sm font-extrabold text-white">
                  0{index + 1}
                </span>
                <h3 className="mt-6 [font-family:var(--font-landing-manrope)] text-lg font-extrabold text-[var(--landing-ink)]">
                  {title}
                </h3>
                <p className="mt-2 text-sm font-medium leading-relaxed text-[var(--landing-muted)]">
                  {description}
                </p>
              </article>
            ))}
          </div>
        </div>
      </section>
      <section className="mx-auto max-w-7xl px-5 py-20 lg:py-24">
        <div className="mx-auto max-w-2xl text-center">
          <p className="landing-eyebrow">Built for trust</p>
          <h2 className="landing-section-title">Why ScrapMart?</h2>
        </div>
        <div className="mt-9 grid gap-4 md:grid-cols-3">
          {benefits.map(([title, icon, description]) => (
            <article
              key={title}
              className="rounded-2xl border border-[var(--landing-line)] bg-white p-6 text-center shadow-[0_5px_20px_rgba(16,42,28,0.035)]"
            >
              <span className="mx-auto grid size-11 place-items-center rounded-xl bg-[var(--landing-brand-soft)] text-[var(--landing-brand)]">
                <Icon name={icon} />
              </span>
              <h3 className="mt-5 [font-family:var(--font-landing-manrope)] text-lg font-extrabold text-[var(--landing-ink)]">
                {title}
              </h3>
              <p className="mx-auto mt-2 max-w-xs text-sm font-medium leading-relaxed text-[var(--landing-muted)]">
                {description}
              </p>
            </article>
          ))}
        </div>
      </section>
      <section
        id="faq"
        className="border-y border-[var(--landing-line)] bg-white px-5 py-20 lg:py-24"
      >
        <div className="mx-auto max-w-3xl">
          <div className="text-center">
            <p className="landing-eyebrow">Common questions</p>
            <h2 className="landing-section-title">
              Frequently asked questions
            </h2>
          </div>
          <div className="mt-9 divide-y divide-[var(--landing-line)] rounded-2xl border border-[var(--landing-line)] bg-white px-5 sm:px-7">
            {faqs.map(([question, answer], index) => {
              const open = openFaq === index;
              return (
                <div key={question} className="py-1">
                  <button
                    onClick={() => setOpenFaq(open ? null : index)}
                    aria-expanded={open}
                    aria-controls={`faq-answer-${index}`}
                    className="flex min-h-16 w-full items-center gap-4 py-3 text-left"
                  >
                    <span className="flex-1 text-sm font-extrabold text-[var(--landing-ink)] sm:text-base">
                      {question}
                    </span>
                    <span
                      className={`grid size-8 shrink-0 place-items-center rounded-full bg-[var(--landing-brand-soft)] text-[var(--landing-brand)] transition-transform duration-200 ${open ? "rotate-45" : ""}`}
                    >
                      <Icon name="plus" className="size-4" />
                    </span>
                  </button>
                  <p
                    hidden={!open}
                    id={`faq-answer-${index}`}
                    className="max-w-2xl pb-5 pr-10 text-sm font-medium leading-relaxed text-[var(--landing-muted)]"
                  >
                    {answer}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      </section>
      <section className="px-5 py-20 lg:py-24">
        <div className="mx-auto max-w-7xl rounded-3xl bg-[var(--landing-brand-dark)] px-6 py-12 text-center text-white shadow-[0_8px_30px_rgba(16,42,28,0.07)] sm:px-10 lg:py-16">
          <h2 className="[font-family:var(--font-landing-manrope)] text-3xl font-extrabold tracking-tight sm:text-4xl">
            Ready to buy or sell scrap?
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-sm font-medium text-slate-200 sm:text-base">
            Join ScrapMart and connect with trusted people in your area.
          </p>
          <div className="mt-7 flex flex-col justify-center gap-3 sm:flex-row">
            <Button
              variant="light"
              href="/signup?role=vendor"
              className="sm:min-w-48"
            >
              I want to sell scrap
            </Button>
            <Button
              variant="outlineLight"
              href="/signup?role=buyer"
              className="sm:min-w-48"
            >
              I want to buy scrap
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}

function HeroMediaSlider() {
  const slides = [
    [
      "/images/hero-slideshow/scrapmart-green-recycling-truck.png",
      "Green ScrapMart truck carrying recyclable plastic bottles",
      "Recycling truck",
    ],
    [
      "/images/hero-slideshow/discarded-air-conditioners.png",
      "Discarded air conditioners and cooling units",
      "Cooling units",
    ],
    [
      "/images/hero-slideshow/used-engines.png",
      "Used engines and automotive components in a salvage yard",
      "Used engines",
    ],
  ];
  const [activeSlide, setActiveSlide] = useState(0);
  const [paused, setPaused] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  useEffect(() => {
    if (
      paused ||
      hovered ||
      focused ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    )
      return;
    const timer = window.setInterval(
      () => setActiveSlide((current) => (current + 1) % slides.length),
      6000,
    );
    return () => window.clearInterval(timer);
  }, [paused, hovered, focused, slides.length]);
  return (
    <div
      role="region"
      aria-roledescription="carousel"
      aria-label="ScrapMart local marketplace"
      className="landing-hero-media relative"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocusCapture={() => setFocused(true)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget))
          setFocused(false);
      }}
    >
      <div className="landing-hero-image h-full overflow-hidden">
        <div className="relative h-full overflow-hidden">
          {slides.map(([src, alt, label], index) => (
            <div
              key={label}
              className={`absolute inset-0 transition-opacity duration-700 ${activeSlide === index ? "opacity-100" : "pointer-events-none opacity-0"}`}
              aria-hidden={activeSlide !== index}
            >
              <Image
                src={src}
                alt={activeSlide === index ? alt : ""}
                fill
                sizes="(min-width: 1280px) 42vw, (min-width: 900px) 48vw, 100vw"
                preload={index === 0}
                className="object-cover"
              />
            </div>
          ))}
          <button
            type="button"
            onClick={() => setPaused(!paused)}
            className="landing-hero-playback absolute right-4 top-4 z-20 min-h-10 rounded-full px-4 text-xs font-bold"
            aria-label={paused ? "Play slideshow" : "Pause slideshow"}
          >
            {paused ? "Play" : "Pause"}
          </button>
          <div className="landing-hero-dots absolute bottom-5 right-5 z-20 flex items-center gap-1.5 rounded-full px-2.5 py-2 shadow">
            {slides.map(([, , label], index) => (
              <button
                key={label}
                onClick={() => setActiveSlide(index)}
                aria-label={`Show ${label} slide`}
                aria-pressed={activeSlide === index}
                className={`min-h-6 rounded-full border-y-8 border-transparent bg-clip-padding transition-all duration-300 ${activeSlide === index ? "w-6 bg-[var(--landing-brand-light)]" : "w-2 bg-white/50 hover:bg-white"}`}
              />
            ))}
          </div>
        </div>
      </div>
      <div className="landing-hero-note absolute bottom-5 left-5 z-20 max-w-xs rounded-2xl p-4 shadow-xl">
        <p className="text-xs font-bold uppercase tracking-widest text-[var(--landing-brand-light)]">
          Safe payment
        </p>
        <p className="mt-1 [font-family:var(--font-landing-manrope)] text-lg font-extrabold text-white">
          Pay only after delivery
        </p>
        <p className="mt-1 text-sm text-[#d0e4d7]">
          Cash, POS or transfer at delivery.
        </p>
      </div>
    </div>
  );
}

export function Welcome() {
  return (
    <main className="landing-page min-h-screen bg-[var(--landing-canvas)] text-[var(--landing-ink)]">
      <div className="bg-[var(--landing-brand-dark)] px-4 py-2 text-center text-xs font-bold text-white">
        PAY ON DELIVERY · Never pay before receiving your item
      </div>
      <LandingHeader />
      <section className="landing-hero mx-4 mb-12 mt-8 max-w-7xl sm:mx-6 2xl:mx-auto" aria-labelledby="landing-hero-title">
        <div className="landing-hero-copy max-w-2xl">
          <Badge>Nigerian marketplace prototype</Badge>
          <h1 id="landing-hero-title" className="landing-hero-title mt-5 [font-family:var(--font-landing-manrope)] font-extrabold leading-[1.02] tracking-[-0.04em]">
            Buy and sell scrap,{" "}
            <span className="text-[var(--landing-brand-light)]">simply.</span>
          </h1>
          <p className="landing-hero-description mt-6 max-w-xl text-lg font-medium leading-relaxed">
            Find scrap vendors near you, or turn unused materials into money. No
            advance payment required.
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <Button href="/signup?role=vendor" className="landing-hero-primary min-w-48">
              I want to sell scrap
            </Button>
            <Button
              variant="ghost"
              href="/signup?role=buyer"
              className="landing-hero-secondary min-w-48"
            >
              I want to buy scrap
            </Button>
          </div>
          <div className="landing-hero-points mt-8 flex flex-wrap gap-x-6 gap-y-3 text-sm font-bold">
            <span className="flex items-center gap-2">
              <Icon
                name="check"
                className="size-4 text-[var(--landing-brand-light)]"
              />
              Vendor verification planned
            </span>
            <span className="flex items-center gap-2">
              <Icon
                name="check"
                className="size-4 text-[var(--landing-brand-light)]"
              />
              Pay on delivery
            </span>
            <span className="flex items-center gap-2">
              <Icon
                name="check"
                className="size-4 text-[var(--landing-brand-light)]"
              />
              Local sellers
            </span>
          </div>
        </div>
        <HeroMediaSlider />
      </section>
      <section
        aria-label="Illustrative marketplace statistics"
        className="border-t border-[var(--landing-line)] bg-white px-5 py-8"
      >
        <p className="mb-4 text-center text-xs font-semibold text-[var(--landing-muted)]">
          Demo figures · illustrative, not live marketplace totals
        </p>
        <div className="mx-auto grid max-w-7xl gap-5 md:grid-cols-3">
          {[
            ["1,200+", "Marketplace listings"],
            ["500+", "Verified vendors"],
            ["10+", "Cities covered"],
          ].map(([a, b]) => (
            <div key={b} className="text-center">
              <p className="[font-family:var(--font-landing-manrope)] text-2xl font-extrabold text-[var(--landing-ink)]">
                {a}
              </p>
              <p className="text-sm font-semibold text-[var(--landing-muted)]">
                {b}
              </p>
            </div>
          ))}
        </div>
      </section>
      <OnboardingSections />
      <OnboardingFooter />
    </main>
  );
}
