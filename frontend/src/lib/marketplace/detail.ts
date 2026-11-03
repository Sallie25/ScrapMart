import type { CatalogueListing } from "./catalogue";

// Only a consented public site with directions enabled receives a map link.
export function publicLocation(listing: Pick<CatalogueListing, "location_summary" | "location_visibility" | "directions_allowed" | "latitude" | "longitude">) {
  const directionsUrl = listing.location_visibility === "public_site" && listing.directions_allowed
    ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${listing.latitude},${listing.longitude}`)}`
    : null;
  return { summary: listing.location_summary, directionsUrl };
}
