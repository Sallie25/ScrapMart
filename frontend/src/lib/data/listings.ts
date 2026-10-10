
export type ScrapListing = {
  id: string;
  title: string;
  category: string;
  price: number;
  unit: string;
  condition: string;
  location: string;
  vendorName: string;
  verifiedVendor: boolean;
  quantity: string;
  description: string;
};

export const demoListings: ScrapListing[] = [
  {
    id: "listing-001",
    title: "Clean Aluminium Scrap",
    category: "Metals",
    price: 3200,
    unit: "kg",
    condition: "Good",
    location: "Ikeja, Lagos",
    vendorName: "Ade Metals",
    verifiedVendor: true,
    quantity: "Approximately 250 kg",
    description: "Sorted aluminium scrap available for collection.",
  },
  {
    id: "listing-002",
    title: "Used Plastic Bottles",
    category: "Plastics",
    price: 450,
    unit: "kg",
    condition: "Used",
    location: "Agege, Lagos",
    vendorName: "Green Point Traders",
    verifiedVendor: true,
    quantity: "Approximately 100 kg",
    description: "Collected plastic bottles, sorted and ready for pickup.",
  },
  {
    id: "listing-003",
    title: "Copper Wire Offcuts",
    category: "Metals",
    price: 8500,
    unit: "kg",
    condition: "Good",
    location: "Oshodi, Lagos",
    vendorName: "Kunle Scrap Hub",
    verifiedVendor: true,
    quantity: "Approximately 35 kg",
    description: "Copper wire offcuts suitable for material recovery.",
  },
  {
    id: "listing-004",
    title: "Used Cardboard Bundles",
    category: "Paper",
    price: 300,
    unit: "kg",
    condition: "Used",
    location: "Yaba, Lagos",
    vendorName: "City Recyclables",
    verifiedVendor: false,
    quantity: "Approximately 180 kg",
    description: "Flattened cardboard bundles for recycling.",
  },
  {
    id: "listing-005",
    title: "Iron and Steel Scrap",
    category: "Metals",
    price: 950,
    unit: "kg",
    condition: "Mixed",
    location: "Ikorodu, Lagos",
    vendorName: "Mainland Metal Works",
    verifiedVendor: true,
    quantity: "Approximately 500 kg",
    description: "Mixed iron and steel scrap for metal recovery.",
  },
  {
    id: "listing-006",
    title: "Faulty Electric Motors",
    category: "Electronics",
    price: 4500,
    unit: "piece",
    condition: "Faulty",
    location: "Mushin, Lagos",
    vendorName: "Tech Scrap Depot",
    verifiedVendor: false,
    quantity: "12 pieces",
    description: "Faulty motors sold as scrap; inspect before purchase.",
  },
];