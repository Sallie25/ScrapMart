"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { VendorIcon } from "./vendor-icon";
const nav = [
  ["Overview", "/vendor/dashboard", "home"],
  ["My Listings", "/vendor/listings", "store"],
  ["Add New Item", "/vendor/listings/new", "plus"],
  ["Customer Orders", "/vendor/dashboard?view=orders", "orders"],
  ["Messages", "/vendor/dashboard?view=messages", "message"],
] as const;
export function VendorNavigation() {
  const view = useSearchParams().get("view");
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
      href="/vendor/dashboard"
      onClick={() => setOpen(false)}
      className="flex items-center gap-2"
    >
      <span className="vendor-dark grid size-9 place-items-center rounded-xl text-white">
        <VendorIcon name="store" />
      </span>
      <span className="vendor-display text-xl font-extrabold tracking-tight">
        Scrap<span className="vendor-green">Mart</span>
      </span>
    </Link>
  );
  const links = (
    <>
      <p className="vendor-muted px-3 text-[10px] font-extrabold uppercase tracking-[.18em]">
        Workspace
      </p>
      <nav aria-label="Vendor workspace" className="mt-2.5 grid gap-1">
        {nav.map(([label, href, icon]) => (
          <Link
            key={href}
            href={href}
            className="vendor-nav-link"
            aria-current={
              (
                href.includes("?")
                  ? href === `/vendor/dashboard?view=${view}`
                  : (!view || view === "local") && path === href
              )
                ? "page"
                : undefined
            }
            onClick={() => setOpen(false)}
          >
            <span className="grid size-8 shrink-0 place-items-center rounded-xl bg-black/5">
              <VendorIcon name={icon} className="size-[18px]" />
            </span>
            {label}
          </Link>
        ))}
      </nav>
      <p className="vendor-muted mt-6 px-3 text-[10px] font-extrabold uppercase tracking-[.18em]">
        Account
      </p>
      <div className="mt-2.5 grid gap-1">
        {[
          ["My Profile", "profile", "user"],
          ["Settings", "settings", "settings"],
        ].map(([label, view, icon]) => (
          <Link
            className="vendor-nav-link"
            key={view}
            href={`/vendor/dashboard?view=${view}`}
            onClick={() => setOpen(false)}
          >
            <VendorIcon name={icon} className="size-[18px]" />
            {label}
          </Link>
        ))}
        <Link
          href="/"
          className="vendor-nav-link"
          onClick={() => setOpen(false)}
        >
          ScrapMart home
        </Link>
        <Link
          href="/login?role=vendor"
          className="vendor-nav-link"
          onClick={() => setOpen(false)}
        >
          Log in
        </Link>
      </div>
    </>
  );
  return (
    <>
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 flex-col border-r border-[#dfe6e1]/80 bg-white/95 shadow-[8px_0_32px_rgba(16,42,28,0.035)] backdrop-blur-xl lg:flex">
        <div className="flex h-20 items-center px-6">{logo}</div>
        <div className="flex-1 overflow-y-auto px-4 pt-4">{links}</div>
        <div className="p-4">
          <div className="vendor-dark rounded-2xl p-4 text-white">
            <p className="text-sm font-bold">Vendor presentation</p>
            <p className="mt-1 text-xs text-slate-300">
              Sample workspace · Not signed in
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
            aria-controls="vendor-mobile-menu"
            className="grid size-10 shrink-0 place-items-center rounded-xl bg-[#f5f7f5] lg:hidden"
          >
            <VendorIcon name="menu" />
          </button>
          <div className="lg:hidden">{logo}</div>
          <div className="hidden lg:block">
            <p className="vendor-muted text-[11px] font-bold">
              Vendor workspace · Preview
            </p>
            <p className="vendor-display text-base font-extrabold">
              {view
                ? ({
                    orders: "Customer Orders",
                    messages: "Messages",
                    bulk: "Add multiple items",
                    profile: "Vendor Profile",
                    settings: "Store Settings",
                    location: "Shop Location",
                    notifications: "Notifications",
                  }[view] ?? "Vendor workspace")
                : path === "/vendor/listings/new"
                  ? "Add New Item"
                  : path === "/vendor/listings"
                    ? "My Listings"
                    : "Vendor Overview"}
            </p>
          </div>
          <span className="vendor-soft ml-auto hidden rounded-full px-3 py-1.5 text-[10px] font-extrabold text-[#064829] sm:block">
            PAY ON DELIVERY
          </span>
          <Link
            href="/vendor/dashboard?view=notifications"
            aria-label="Open notifications"
            className="grid size-10 shrink-0 place-items-center rounded-full bg-[#f5f7f5] max-sm:ml-auto"
          >
            <VendorIcon name="bell" className="size-[18px]" />
          </Link>
          <Link
            href="/vendor/dashboard?view=profile"
            aria-label="Open profile"
            className="vendor-dark grid size-9 shrink-0 place-items-center rounded-full text-[11px] font-extrabold text-white"
          >
            Demo
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
            id="vendor-mobile-menu"
            role="dialog"
            aria-modal="true"
            aria-label="Vendor navigation"
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
                <VendorIcon name="close" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-4 py-5">{links}</div>
          </aside>
        </div>
      )}
    </>
  );
}
