import { demoListings, type ScrapListing } from "./listings";

// Approved App.tsx sample content. These are presentation fixtures, not API DTOs.
export type BuyerListing = ScrapListing & { image?: string };
const samples = [
  [
    "toyota-engine",
    "Toyota Camry Engine",
    "Car Parts",
    450000,
    "Used",
    "Ikeja, Lagos",
    "engine",
    "Akin Auto Parts",
  ],
  [
    "honda-engine",
    "Honda Accord Engine",
    "Car Parts",
    280000,
    "Faulty",
    "Agege, Lagos",
    "engine2",
    "Chuks Motor Spares",
  ],
  [
    "copper-wire",
    "Copper Wire Bundle",
    "Copper",
    90000,
    "Good condition",
    "Alaba, Lagos",
    "wires",
    "Akin Auto Parts",
  ],
  [
    "machinery-parts",
    "Mixed Machinery Parts",
    "Machinery",
    175000,
    "For parts",
    "Oshodi, Lagos",
    "parts",
    "Musa Industrial",
  ],
  [
    "metal-lot",
    "Scrap Metal Lot",
    "Scrap Metal",
    125000,
    "Used",
    "Mushin, Lagos",
    "metal",
    "Greenline Metals",
  ],
  [
    "generator-engine",
    "Used Generator Engine",
    "Machinery",
    210000,
    "Faulty",
    "Ikorodu, Lagos",
    "mechanic",
    "Akin Auto Parts",
  ],
  [
    "clothes",
    "Quality Second-Hand Clothes",
    "Clothes",
    65000,
    "Good condition",
    "Yaba, Lagos",
    "clothes",
    "Bisi Clothing Hub",
  ],
] as const;
export const designerListings: BuyerListing[] = samples.map(
  (
    [id, title, category, price, condition, location, image, vendorName],
    index,
  ) => ({
    id: `demo-${id}`,
    title,
    category,
    price,
    condition,
    location,
    image: `/images/buyer/${image}.jpg`,
    vendorName,
    verifiedVendor: false,
    unit: "lot",
    quantity: "1 sample lot",
    description: `Presentation fixture: ${title}. Availability, condition, quantity and vendor identity are sample data, not live marketplace information.`,
    createdAt: `2026-10-${String(25 - index).padStart(2, "0")}T10:00:00`,
  }),
);
// Keep all prior IDs/data available; never replace the existing marketplace fixtures.
export const buyerListings: BuyerListing[] = [
  ...designerListings,
  ...demoListings,
];
export const buyerCategories = [
  ["Clothes", "clothes", "Clothes"],
  ["Scrap Metal", "category-scrap-metal", "Scrap Metal"],
  ["Aluminium", "category-aluminium", "Metals"],
  ["Copper", "wires", "Copper"],
  ["Iron", "category-iron", "Metals"],
  ["Electronics", "category-electronics", "Electronics"],
  ["Car Parts", "engine", "Car Parts"],
  ["Machinery", "category-machinery", "Machinery"],
  ["Batteries", "category-batteries", null],
  ["Plastics", "category-plastics", "Plastics"],
  ["Other", "parts", null],
] as const;
export function vendorSlug(name: string) {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}
