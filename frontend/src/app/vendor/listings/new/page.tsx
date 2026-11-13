import { VendorListingForm } from "@/components/vendor/vendor-listing-form";
import { marketplaceClient } from "@/lib/server/marketplace/client";

export default async function NewVendorListingPage() {
  let categories;
  try { categories = await marketplaceClient().categories(); }
  catch { return <section role="alert" className="vendor-card p-6">Categories are unavailable. Creating a listing requires live categories; please try again.</section>; }
  return <VendorListingForm categories={categories} />;
}
