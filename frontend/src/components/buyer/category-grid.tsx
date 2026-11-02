import Link from "next/link";
import Image from "next/image";
import { buyerCategories } from "@/lib/data/buyer-fixtures";
export function CategoryGrid() {
  return (
    <div className="mt-5 grid grid-cols-3 gap-3 sm:grid-cols-5 lg:grid-cols-11">
      {buyerCategories.map(([label, image, category]) => (
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
            <Image
              src={`/images/buyer/${image}.jpg`}
              alt={`${label} category presentation image`}
              width={120}
              height={120}
              sizes="(max-width:640px) 30vw, (max-width:1024px) 15vw, 8vw"
              className="aspect-square w-full object-cover transition group-hover:scale-105"
            />
          </span>
          <span className="mt-2 block break-words pb-1 text-xs font-bold">
            {label}
          </span>
        </Link>
      ))}
    </div>
  );
}
