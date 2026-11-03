import { BuyerShell } from "@/components/buyer/buyer-shell";
export default function Loading() {
  return <BuyerShell variant="public" publicNotice="Loading live marketplace listings…"><div role="status" className="buyer-card p-10 text-center"><h1 className="buyer-title">Find scrap</h1><p className="buyer-muted mt-4">Loading live listings…</p></div></BuyerShell>;
}
