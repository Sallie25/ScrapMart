import { VendorListingForm } from "@/components/vendor/vendor-listing-form";
import { marketplaceClient } from "@/lib/server/marketplace/client";

export default async function EditVendorListingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let categories;
  try { categories = await marketplaceClient().categories(); }
  catch { return <section role="alert" className="vendor-card p-6">Categories are unavailable. Editing this listing requires live categories; please try again.</section>; }
  return <VendorListingForm categories={categories} listingId={id} />;
}
