export type VendorDemoListing = {
  id: string;
  title: string;
  vendorName?: string;
  category: string;
  condition: string;
  description: string;
  price: number;
  unit: string;
  quantity: number;
  location: string;
  photoName: string;
  createdAt: string;
};

const STORAGE_KEY = "scrapmart-vendor-demo-listings";

function isVendorDemoListing(value: unknown): value is VendorDemoListing {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }

  const listing = value as Record<string, unknown>;
  const stringFields = [
    "id", "title", "category", "condition", "description",
    "unit", "location", "photoName", "createdAt",
  ];

  return (
    stringFields.every((field) => typeof listing[field] === "string") &&
    typeof listing.id === "string" && listing.id.trim().length > 0 &&
    typeof listing.price === "number" && Number.isFinite(listing.price) &&
    typeof listing.quantity === "number" && Number.isFinite(listing.quantity) &&
    (!("vendorName" in listing) || typeof listing.vendorName === "string")
  );
}

function readVendorDemoListingsStrict(): VendorDemoListing[] {
  if (typeof window === "undefined") {
    throw new Error("Browser listing storage is unavailable.");
  }

  const stored = window.localStorage.getItem(STORAGE_KEY);

  if (stored === null) {
    return [];
  }

  const parsed: unknown = JSON.parse(stored);

  if (!Array.isArray(parsed)) {
    throw new Error("Saved demo listings must be an array.");
  }

  const ids = new Set<string>();
  for (const listing of parsed) {
    if (!isVendorDemoListing(listing) || ids.has(listing.id)) {
      throw new Error("Saved demo listings contain invalid or duplicate records.");
    }
    ids.add(listing.id);
  }

  return parsed;
}

export function getVendorDemoListings(): VendorDemoListing[] {
  try {
    return readVendorDemoListingsStrict();
  } catch {
    return [];
  }
}

export function hasVendorDemoListing(id: string): boolean {
  return readVendorDemoListingsStrict().some((listing) => listing.id === id);
}

function notifyListingsUpdated(): void {
  try {
    window.dispatchEvent(new Event("scrapmart-demo-listings-updated"));
  } catch {
    // Metadata is committed. Notification failure must not trigger photo rollback.
  }
}

export function saveVendorDemoListing(
  listing: VendorDemoListing,
): void {
  const listings = readVendorDemoListingsStrict();

  if (listings.some((existing) => existing.id === listing.id)) {
    throw new Error("A demo listing with this ID already exists.");
  }

  window.localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify([listing, ...listings]),
  );

  notifyListingsUpdated();
}

export function deleteVendorDemoListing(id: string): { removed: boolean } {
  const listings = readVendorDemoListingsStrict();
  const remaining = listings.filter((listing) => listing.id !== id);

  if (remaining.length === listings.length) {
    return { removed: false };
  }

  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(remaining));
  notifyListingsUpdated();
  return { removed: true };
}
