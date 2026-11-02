import { VendorWorkspace } from "@/components/vendor/vendor-workspace";
export default async function VendorListings({
  searchParams,
}: {
  searchParams: Promise<{ view?: string }>;
}) {
  const { view } = await searchParams;
  return <VendorWorkspace view={view === "local" ? "local" : "listings"} />;
}
