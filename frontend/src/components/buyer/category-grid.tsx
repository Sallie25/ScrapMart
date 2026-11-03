import Link from "next/link";
import { MaterialVisual } from "@/components/marketplace/material-visual";
import { buyerCategories } from "@/lib/data/buyer-fixtures";
export function CategoryGrid() {
  return (
    <div className="mt-5 grid grid-cols-3 gap-3 sm:grid-cols-5 lg:grid-cols-11">
      {buyerCategories.map(([label, , category]) => (
        <Link
          key={label}
          href={
            category
              ? `/marketplace?category=${encodeURIComponent(category)}`
              : `/marketplace?q=${encodeURIComponent(label)}`
          }
          className="group min-w-0 overflow-hidden rounded-2xl border border-[#dfe6e1] bg-white p-2 text-center transition hover:border-[#08783e]/40 hover:shadow-lg"
        >
          <span className="block overflow-hidden rounded-xl bg-[#f5f7f5]">
            <span className="block aspect-square w-full">
              <MaterialVisual category={label} compact />
            </span>
          </span>
          <span className="mt-2 block break-words pb-1 text-xs font-bold">
            {label}
          </span>
        </Link>
      ))}
    </div>
  );
}
