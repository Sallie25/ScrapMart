import Image from "next/image";
import { getMaterial } from "@/lib/media/materials";
import { MaterialPlaceholder } from "./material-placeholder";

// Category context only: generated images never document a seller's stock.
export function MaterialVisual({
  category,
  title = "",
  compact = false,
  inventory = false,
}: {
  category: string;
  title?: string;
  compact?: boolean;
  inventory?: boolean;
}) {
  const material = getMaterial(category, title);
  const assets: Partial<Record<ReturnType<typeof getMaterial>, string>> = {
    clothes: "clothes",
    cardboard: "cardboard",
    bottles: "bottles",
    plastics: "bottles",
    iron: "iron",
    electronics: "electronics",
    aluminium: "aluminium",
    copper: "copper",
    tyres: "tyres",
  };
  const asset = assets[material];
  if (!asset)
    return (
      <MaterialPlaceholder
        category={category}
        title={title}
        compact={compact}
      />
    );
  return (
    <span
      className="relative block h-full w-full overflow-hidden"
      data-generated-material={material}
    >
      <Image
        src={`/images/generated/${asset}.webp`}
        alt={`${title || category} — AI-generated material illustration, not actual seller inventory or a real location`}
        fill
        sizes={
          compact
            ? "(max-width: 639px) 30vw, 120px"
            : "(max-width: 639px) 100vw, (max-width: 1023px) 50vw, 560px"
        }
        className="object-cover"
      />
      <span
        className={`absolute inset-x-0 bg-[#102a1c]/95 px-2 py-1 text-center font-semibold leading-snug text-white ${compact ? "bottom-0 text-[9px]" : "top-0 text-xs"}`}
      >
        AI illustration{inventory && !compact ? " · Not seller inventory" : ""}
      </span>
    </span>
  );
}
