import type { ReactNode } from "react";
import { getMaterial } from "@/lib/media/materials";

// Code-native illustrations, never documentary or seller-stock photographs.
export function MaterialPlaceholder({
  category,
  title = "",
  compact = false,
}: {
  category: string;
  title?: string;
  compact?: boolean;
}) {
  const material = getMaterial(category, title);
  const drawings: Record<ReturnType<typeof getMaterial>, ReactNode> = {
    bottles: (
      <>
        <path d="M39 8h18v9l6 10v32a7 7 0 0 1-7 7H40a7 7 0 0 1-7-7V27l6-10Z" />
        <path d="M39 16h18M34 35h28M34 51h28M42 8V4h12v4" />
      </>
    ),
    plastics: (
      <>
        <path d="M19 27h25l-3 34H22ZM23 20h17v7H23ZM55 18h18v8l5 8v27H51V34l4-8Z" />
        <path d="M53 43h23M54 51h21M25 38h12" />
      </>
    ),
    tyres: (
      <>
        <ellipse cx="35" cy="36" rx="19" ry="27" />
        <ellipse cx="35" cy="36" rx="8" ry="15" />
        <path d="M35 9h23c25 0 25 54 0 54H35M65 15l-7 7M72 29l-9 5M72 45l-9 2M65 59l-8-4" />
      </>
    ),
    rubber: (
      <>
        <path d="m19 27 31-12 29 16-32 13Z" />
        <path d="m19 38 28 17 32-13M19 49l28 17 32-13M19 27v22M79 31v22" />
      </>
    ),
    metal: (
      <>
        <path d="m14 30 16-12 48 11-17 12ZM14 30v9l47 12 17-13v-9M24 47v10l37 10 18-13V44M38 23l-7 11M55 27l-7 11" />
      </>
    ),
    copper: (
      <>
        <path d="M23 22c-17 0-17 33 0 33h43c18 0 18-33 0-33Z" />
        <ellipse cx="25" cy="38" rx="11" ry="16" />
        <path d="M24 29c-7 0-7 17 0 17M39 23v31M51 23v31M64 23v31M65 55l13 9M70 52l14 5" />
      </>
    ),
    aluminium: (
      <>
        <path d="M23 20h21l-3 39H25ZM53 28h20l-2 31H55Z" />
        <ellipse cx="33.5" cy="20" rx="10.5" ry="4" />
        <ellipse cx="63" cy="28" rx="10" ry="4" />
        <path d="m25 34 15 8-13 5M55 42l15 5" />
      </>
    ),
    iron: (
      <>
        <path
          d="m16 21 30-9 33 17-30 9ZM16 21v9l11 6v17l-11-5v9l33 16 30-10v-9l-11 4V39l11-3v-7M49 38v9l-10-5v17l10 5v9M49 47l19-8M49 64l19-6"
          transform="translate(0 -5)"
        />
      </>
    ),
    electronics: (
      <>
        <rect x="14" y="13" width="48" height="34" rx="4" />
        <path d="M20 19h36v21H20ZM31 47v9M45 47v9M25 56h26" />
        <rect x="67" y="26" width="17" height="35" rx="3" />
        <path d="M73 33h5M73 39h5M73 53h5M18 64h40" />
      </>
    ),
    paper: (
      <>
        <path d="M25 12h35l13 13v36H25ZM60 12v14h13M32 34h30M32 42h25M32 50h29M18 20v47h46" />
      </>
    ),
    cardboard: (
      <>
        <path d="m17 26 30-13 32 13-32 14ZM17 26v30l30 14 32-14V26M47 40v30M32 20l31 14v11l-14-6" />
      </>
    ),
    motor: (
      <>
        <ellipse cx="28" cy="37" rx="15" ry="21" />
        <ellipse cx="28" cy="37" rx="7" ry="11" />
        <path d="M28 16h35l15 12v30H28M43 23v27M54 23v27M65 29v21M13 37H5v7h10M40 58v8h30v-8" />
      </>
    ),
    engine: (
      <>
        <path d="M27 25h37v9h13v22H60v9H29V55H17V33h10ZM32 17h27v8M42 11v6M22 41h-8M77 40h7v16h-7M35 35l12 8-8 8h14" />
      </>
    ),
    machinery: (
      <>
        <path d="m41 11 3 8h9l3-8 9 5-4 8 5 7 9-1v11l-9-1-5 7 4 8-9 5-3-8h-9l-3 8-9-5 4-8-5-7-9 1V30l9 1 5-7-4-8Z" />
        <circle cx="48" cy="35" r="11" />
      </>
    ),
    batteries: (
      <>
        <rect x="18" y="24" width="59" height="35" rx="4" />
        <path d="M26 24v-7h13v7M58 24v-7h11v7M26 39h12M32 33v12M58 39h11" />
      </>
    ),
    clothes: (
      <>
        <path d="m32 14-17 9 8 18 10-5v29h30V36l10 5 8-18-17-9c-3 12-29 12-32 0Z" />
        <path d="M33 36v-9M63 36v-9" />
      </>
    ),
    glass: (
      <>
        <path d="M33 8h27v12l7 10v27a7 7 0 0 1-7 7H33a7 7 0 0 1-7-7V30l7-10ZM34 18h25M34 35v18M41 28h11" />
      </>
    ),
    other: (
      <>
        <path d="m16 28 21-12 22 12-22 12ZM16 28v24l21 12V40M37 64l22-12V28M63 16h15v13H63ZM65 39h16v22H65Z" />
      </>
    ),
  };
  const label = title || category;
  const materialLabels: Record<ReturnType<typeof getMaterial>, string> = {
    bottles: "Plastic bottles",
    plastics: "Plastics",
    tyres: "Tyres",
    rubber: "Rubber",
    metal: "Mixed metal",
    copper: "Copper wire",
    aluminium: "Aluminium",
    iron: "Iron & steel",
    electronics: "Electronic waste",
    paper: "Paper",
    cardboard: "Cardboard",
    engine: "Engine parts",
    motor: "Electric motor",
    machinery: "Machinery parts",
    batteries: "Batteries",
    clothes: "Clothing",
    glass: "Glass",
    other: category,
  };
  return (
    <div
      role="img"
      aria-label={`${label}: illustrative material drawing; photograph unavailable`}
      data-material={material}
      className={`relative flex h-full w-full flex-col items-center justify-center overflow-hidden bg-[radial-gradient(ellipse_at_top_right,#d0efdc,transparent_65%),linear-gradient(135deg,#f5faf6,#e8f7ee)] text-[#08783e] ${compact ? "gap-1 p-1" : "gap-3 p-4"}`}
    >
      <svg
        aria-hidden="true"
        viewBox="0 0 96 80"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        className={
          compact ? "max-h-[65%] w-3/5 max-w-16" : "max-h-[48%] w-2/5 max-w-44"
        }
      >
        <circle
          cx="48"
          cy="38"
          r="34"
          fill="#fff"
          fillOpacity=".6"
          stroke="none"
        />
        {drawings[material]}
      </svg>
      {!compact && (
        <span className="max-w-full text-center text-sm font-extrabold sm:text-base">
          {title ? materialLabels[material] : category}
        </span>
      )}
      <span
        className={`max-w-full rounded-full bg-white/90 text-center font-semibold text-[#4c6557] ${compact ? "px-1 text-[8px] leading-tight" : "px-3 py-1 text-[10px] sm:text-xs"}`}
      >
        {compact ? "Illustration" : "Illustration · Photo unavailable"}
      </span>
    </div>
  );
}
