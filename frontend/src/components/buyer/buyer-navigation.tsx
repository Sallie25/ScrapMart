"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BuyerIcon } from "./buyer-icon";
import { BuyerLogoutButton } from "./buyer-logout-button";
const nav = [
  ["Overview", "/buyer/dashboard", "home"],
  ["Browse Marketplace", "/marketplace", "search"],
  ["My Orders", "/buyer/dashboard?view=orders", "orders"],
  ["Messages", "/buyer/dashboard?view=messages", "message"],
] as const;
export function BuyerNavigation({ view, authenticated = false }: { view?: string; authenticated?: boolean }) {
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const trigger = triggerRef.current;
    closeRef.current?.focus();
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
      trigger?.focus();
    };
  }, [open]);
  const logo = (
    <Link
      href="/buyer/dashboard"
      onClick={() => setOpen(false)}
      className="flex items-center gap-2"
    >
      <span className="buyer-dark grid size-9 place-items-center rounded-xl text-white">
        <BuyerIcon name="store" />
      </span>
      <span className="buyer-display text-xl font-extrabold tracking-tight">
        Scrap<span className="buyer-green">Mart</span>
      </span>
    </Link>
  );
  const links = (
    <>
      <p className="buyer-muted px-3 text-[10px] font-extrabold uppercase tracking-[.18em]">
        Workspace
      </p>
      <nav aria-label="Buyer workspace" className="mt-2.5 grid gap-1">
        {nav.map(([label, href, icon]) => (
          <Link
            key={href}
            href={href}
            className="buyer-nav-link"
            aria-current={
              (
                href.includes("?")
                  ? href === `/buyer/dashboard?view=${view}`
                  : (!view && path === href) ||
                    (href === "/marketplace" && path.startsWith("/listings/"))
              )
                ? "page"
                : undefined
            }
            onClick={() => setOpen(false)}
          >
            <span className="grid size-8 shrink-0 place-items-center rounded-xl bg-black/5">
              <BuyerIcon name={icon} className="size-[18px]" />
            </span>
            {label}
          </Link>
        ))}
      </nav>
      <p className="buyer-muted mt-6 px-3 text-[10px] font-extrabold uppercase tracking-[.18em]">
        Account
      </p>
      <div className="mt-2.5 grid gap-1">
        {[
          ["My Profile", "profile", "user"],
          ["Settings", "settings", "settings"],
        ].map(([label, view, icon]) => (
          <Link
            className="buyer-nav-link"
            key={view}
            href={`/buyer/dashboard?view=${view}`}
            onClick={() => setOpen(false)}
          >
            <BuyerIcon name={icon} className="size-[18px]" />
            {label}
          </Link>
        ))}
        <Link
          href="/"
          className="buyer-nav-link"
          onClick={() => setOpen(false)}
        >
          ScrapMart home
        </Link>
        {authenticated ? <BuyerLogoutButton /> : <Link
          href="/login?role=buyer"
          className="buyer-nav-link"
          onClick={() => setOpen(false)}
        >Log in</Link>}
      </div>
    </>
  );
  return (
    <>
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 flex-col border-r border-[#dfe6e1]/80 bg-white/95 shadow-[8px_0_32px_rgba(16,42,28,0.035)] backdrop-blur-xl lg:flex">
        <div className="flex h-20 items-center px-6">{logo}</div>
        <div className="flex-1 overflow-y-auto px-4 pt-4">{links}</div>
        <div className="p-4">
          <div className="buyer-dark rounded-2xl p-4 text-white">
            <p className="text-sm font-bold">Buyer workspace</p>
            <p className="mt-1 text-xs text-slate-300">
              {authenticated ? "Signed in · Account data preview" : "Sample workspace · Not signed in"}
            </p>
          </div>
        </div>
      </aside>
      <header className="sticky top-0 z-30 border-b border-[#dfe6e1]/80 bg-white/85 backdrop-blur-xl lg:ml-64">
        <div className="flex h-16 items-center gap-3 px-4 lg:h-20 lg:px-7">
          <button
            ref={triggerRef}
            type="button"
            onClick={() => setOpen(true)}
            aria-label="Open navigation menu"
            aria-expanded={open}
            aria-controls="buyer-mobile-menu"
            className="grid size-10 shrink-0 place-items-center rounded-xl bg-[#f5f7f5] lg:hidden"
          >
            <BuyerIcon name="menu" />
          </button>
          <div className="lg:hidden">{logo}</div>
          <div className="hidden lg:block">
            <p className="buyer-muted text-[11px] font-bold">
              {authenticated ? "Buyer workspace" : "Buyer workspace · Preview"}
            </p>
            <p className="buyer-display text-base font-extrabold">
              {path === "/buyer/dashboard"
                ? "Buyer Overview"
                : path === "/marketplace"
                  ? "Browse Marketplace"
                  : "Item Details"}
            </p>
          </div>
          <span className="buyer-soft ml-auto hidden rounded-full px-3 py-1.5 text-[10px] font-extrabold text-[#064829] sm:block">
            PAY ON DELIVERY
          </span>
          <Link
            href="/buyer/dashboard?view=notifications"
            aria-label="Open notifications"
            className="grid size-10 shrink-0 place-items-center rounded-full bg-[#f5f7f5] max-sm:ml-auto"
          >
            <BuyerIcon name="bell" className="size-[18px]" />
          </Link>
          <Link
            href="/buyer/dashboard?view=profile"
            aria-label="Open profile"
            className="buyer-dark grid size-9 shrink-0 place-items-center rounded-full text-[11px] font-extrabold text-white"
          >
            {authenticated ? "Buyer" : "Demo"}
          </Link>
        </div>
      </header>
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="Close navigation overlay"
            onClick={() => setOpen(false)}
            className="absolute inset-0 bg-[#14211a]/45 backdrop-blur-sm"
          />
          <aside
            id="buyer-mobile-menu"
            role="dialog"
            aria-modal="true"
            aria-label="Buyer navigation"
            onKeyDown={(event) => {
              if (event.key === "Escape") setOpen(false);
              if (event.key === "Tab") {
                const elements =
                  event.currentTarget.querySelectorAll<HTMLElement>("a,button");
                const first = elements[0],
                  last = elements[elements.length - 1];
                if (event.shiftKey && document.activeElement === first) {
                  event.preventDefault();
                  last.focus();
                } else if (!event.shiftKey && document.activeElement === last) {
                  event.preventDefault();
                  first.focus();
                }
              }
            }}
            className="absolute inset-y-0 left-0 flex w-[86%] max-w-sm flex-col bg-white shadow-2xl"
          >
            <div className="flex h-16 shrink-0 items-center justify-between border-b border-[#dfe6e1] px-5">
              {logo}
              <button
                ref={closeRef}
                type="button"
                aria-label="Close navigation menu"
                onClick={() => setOpen(false)}
                className="grid size-9 place-items-center rounded-xl bg-[#f5f7f5]"
              >
                <BuyerIcon name="close" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-4 py-5">{links}</div>
          </aside>
        </div>
      )}
    </>
  );
}
