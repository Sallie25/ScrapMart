import { BuyerShell } from "@/components/buyer/buyer-shell";
import { ListingDetails } from "@/components/buyer/listing-details";
export default async function ListingDetailsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <BuyerShell variant="public">
      <ListingDetails key={id} id={id} />
    </BuyerShell>
  );
}
