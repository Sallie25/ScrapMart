export type BuyerAction = "contact" | "order";

// Accept only an internal, encoded listing path and the two known intents.
export function safeListingReturn(value: unknown): string | null {
  if (typeof value !== "string" || value.length > 300) return null;
  const match =
    /^\/listings\/([A-Za-z0-9][A-Za-z0-9_-]{0,99})\?intent=(contact|order)$/.exec(
      value,
    );
  return match && match[0] === value ? value : null;
}
export function buyerActionLogin(id: string, action: BuyerAction): string {
  const destination = safeListingReturn(`/listings/${id}?intent=${action}`);
  return destination
    ? `/login?role=buyer&returnTo=${encodeURIComponent(destination)}`
    : "/login?role=buyer";
}
