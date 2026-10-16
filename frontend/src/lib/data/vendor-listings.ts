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

export function getVendorDemoListings(): VendorDemoListing[] {
  if (typeof window === "undefined") {
    return [];
  }

  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);

    if (!stored) {
      return [];
    }

    const parsed: unknown = JSON.parse(stored);

    if (!Array.isArray(parsed)) {
      return [];
    }

    return parsed as VendorDemoListing[];
  } catch {
    return [];
  }
}

export function saveVendorDemoListing(
  listing: VendorDemoListing,
): void {
  const listings = getVendorDemoListings();

  window.localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify([listing, ...listings]),
  );

  window.dispatchEvent(new Event("scrapmart-demo-listings-updated"));
}

export function deleteVendorDemoListing(id: string): void {
  const remaining = getVendorDemoListings().filter(
    (listing) => listing.id !== id,
  );

  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(remaining));
  window.dispatchEvent(new Event("scrapmart-demo-listings-updated"));
}