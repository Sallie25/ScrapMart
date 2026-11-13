import { VendorLiveListings } from "@/components/vendor/vendor-live-listings";
import { VendorShopProfile } from "@/components/vendor/vendor-shop-profile";
import { AccountMessages } from "@/components/account/account-messages";
import { VendorOrderHistory } from "@/components/vendor/vendor-order-history";

export default async function VendorDashboard({ searchParams }: { searchParams: Promise<{ view?: string }> }) {
  const { view } = await searchParams;
  if (view === "profile" || view === "location" || view === "settings") return <VendorShopProfile />;
  if (view === "messages") return <AccountMessages role="vendor" />;
  if (view === "orders") return <VendorOrderHistory />;
  if (view && view !== "listings") return <section role="status" className="vendor-card p-8"><h1 className="vendor-title">{view === "orders" ? "Customer Orders" : view === "messages" ? "Messages" : "Vendor account"}</h1><p className="vendor-muted mt-3">This account view is not connected yet. No transactions or messages are being shown as completed.</p></section>;
  return <VendorLiveListings overview />;
}
