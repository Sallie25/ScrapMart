"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BuyerIcon } from "./buyer-icon";
const nav = [
  ["Home", "/", "home"],
  ["Marketplace", "/marketplace", "search"],
  ["How it works", "/how-it-works", "orders"],
  ["Log in", "/login?role=buyer", "user"],
] as const;
export function MarketplaceNavigation() {
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
      href="/"
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
    <nav aria-label="Marketplace navigation" className="grid gap-1">
      {nav.map(([label, href, icon]) => (
        <Link
          key={href}
          href={href}
          className="buyer-nav-link"
          onClick={() => setOpen(false)}
          aria-current={
            href === path ||
            (href === "/marketplace" && path.startsWith("/listings/"))
              ? "page"
              : undefined
          }
        >
          <span className="grid size-8 shrink-0 place-items-center rounded-xl bg-black/5">
            <BuyerIcon name={icon} />
          </span>
          {label}
        </Link>
      ))}
    </nav>
  );
  return (
    <>
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 flex-col border-r border-[#dfe6e1]/80 bg-white/95 shadow-[8px_0_32px_rgba(16,42,28,0.035)] backdrop-blur-xl lg:flex">
        <div className="flex h-20 items-center px-6">{logo}</div>
        <div className="flex-1 overflow-y-auto px-4 pt-4">{links}</div>
        <div className="p-4">
          <div className="buyer-dark rounded-2xl p-4 text-white">
            <p className="text-sm font-bold">Public marketplace</p>
            <p className="mt-1 text-xs text-slate-300">
              Browse freely · Sign in for buyer actions
            </p>
          </div>
        </div>
      </aside>
      <header className="sticky top-0 z-30 border-b border-[#dfe6e1]/80 bg-white/95 lg:hidden">
        <div className="flex h-16 items-center gap-3 px-4">
          <button
            ref={triggerRef}
            type="button"
            onClick={() => setOpen(true)}
            aria-label="Open navigation menu"
            aria-expanded={open}
            aria-controls="buyer-mobile-menu"
            className="grid size-10 place-items-center rounded-xl bg-[#f5f7f5]"
          >
            <BuyerIcon name="menu" />
          </button>
          {logo}
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
            aria-label="Marketplace navigation menu"
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
