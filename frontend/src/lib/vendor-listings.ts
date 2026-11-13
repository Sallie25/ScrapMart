import { z } from "zod";
import { categorySchema, resourceId } from "./marketplace/catalogue";

export const ownedListing = z.object({
  id: resourceId, title: z.string(), status: z.enum(["draft", "active", "inactive", "sold", "removed"]),
  category_id: resourceId.nullable(), category: categorySchema.nullable(),
  price: z.string().nullable(), quantity: z.string().nullable(),
  quantity_unit: z.enum(["pieces", "kilograms", "tonnes", "bundles"]).nullable(),
  condition: z.enum(["good_condition", "used", "faulty", "damaged", "for_parts"]).nullable(),
  description: z.string().nullable(), location_summary: z.string().nullable(),
  latitude: z.string().nullable(), longitude: z.string().nullable(),
  photos: z.array(z.object({ id: resourceId, url: z.string() })),
});
export const ownedPage = z.object({ listings: z.array(ownedListing), next_cursor: z.string().nullable() });
export type OwnedListing = z.infer<typeof ownedListing>;

export async function vendorRequest(path: string, options: RequestInit = {}): Promise<Response> {
  const headers = new Headers(options.headers);
  if (options.method && options.method !== "GET") headers.set("X-ScrapMart-CSRF", "1");
  return fetch(`/api/vendor/${path}`, { credentials: "same-origin", cache: "no-store", redirect: "error",
    ...options, headers });
}
