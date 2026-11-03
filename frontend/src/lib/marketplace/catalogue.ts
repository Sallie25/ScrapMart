import { z } from "zod";

// Public DTOs from marketplace.py / MarketplaceService._dto. Never reuse demo types.
export const resourceId = z.string().regex(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
export const conditions = {
  good_condition: "Good condition", used: "Used", faulty: "Faulty",
  damaged: "Damaged", for_parts: "For parts",
} as const;
export const units = {
  pieces: "piece", kilograms: "kilogram", tonnes: "tonne", bundles: "bundle",
} as const;
const money = z.string().regex(/^\d{1,12}\.\d{2}$/);
const quantity = z.string().regex(/^\d{1,11}\.\d{3}$/);
const coordinate = (maximum: number) => z.string().regex(/^-?\d{1,3}\.\d{6}$/)
  .refine(value => Math.abs(Number(value)) <= maximum);
const date = z.iso.datetime({ offset: true });
const photoUrl = z.string().max(2048).refine(value => {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !!url.hostname && !url.username && !url.password &&
      !url.search && !url.hash && /\/listings\/[A-Za-z0-9/_-]{1,200}\.jpg$/.test(url.pathname);
  } catch { return false; }
});
export const categorySchema = z.object({ id: resourceId, name: z.string().min(1).max(100), slug: z.string().min(1).max(120) });
export const listingSchema = z.object({
  id: resourceId, title: z.string().min(1).max(200), description: z.string().max(5000),
  category_id: resourceId, category: categorySchema, status: z.literal("active"),
  price: money, price_type: z.enum(["total", "per_unit"]), currency: z.literal("NGN"),
  is_negotiable: z.boolean(), quantity, available_quantity: quantity,
  quantity_unit: z.enum(["pieces", "kilograms", "tonnes", "bundles"]),
  condition: z.enum(["good_condition", "used", "faulty", "damaged", "for_parts"]),
  location_summary: z.string().min(1).max(255), lga: z.string().nullable(), area: z.string().nullable(),
  latitude: coordinate(90), longitude: coordinate(180),
  location_visibility: z.enum(["approximate", "public_site"]), directions_allowed: z.boolean(),
  vendor: z.object({ business_name: z.string().min(1).max(200), shop_location: z.string(), verified: z.literal(true) }),
  photos: z.array(z.object({ id: resourceId, url: photoUrl, position: z.number().int().min(0).max(4),
    width: z.number().int().positive().nullable(), height: z.number().int().positive().nullable() })).min(1).max(5),
  created_at: date, updated_at: date, published_at: date,
}).refine(value => value.category_id === value.category.id);
export const cursorSchema = z.string().min(1).max(300).regex(/^[A-Za-z0-9_-]+={0,2}$/);
export const listingPageSchema = z.object({ listings: z.array(listingSchema).max(20), next_cursor: cursorSchema.nullable() });
export const categoryPageSchema = z.object({ categories: z.array(categorySchema).max(100), next_cursor: resourceId.nullable() });
export type CatalogueListing = z.infer<typeof listingSchema>;
export type CatalogueCategory = z.infer<typeof categorySchema>;
export type ListingPage = z.infer<typeof listingPageSchema>;

// Format exact decimal strings without dropping kobo or rounding through Number.
export function formatMoney(value: string): string {
  const [whole, fraction] = value.split(".");
  return `₦${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}.${fraction}`;
}
export function formatQuantity(value: string): string {
  return value.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
}
export function priceBasis(listing: Pick<CatalogueListing, "price_type" | "quantity_unit">): string {
  return listing.price_type === "total" ? "total lot price" : `per ${units[listing.quantity_unit]}`;
}
