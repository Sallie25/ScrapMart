import { conditions, cursorSchema, resourceId } from "./catalogue";
import type { CatalogueCategory } from "./catalogue";

export type SearchParameters = Record<string, string | string[] | undefined>;
export type CatalogueQuery = {
  q?: string; category_id?: string; location?: string; condition?: keyof typeof conditions;
  min_price?: string; max_price?: string; cursor?: string; limit?: string; sort?: "recent"; verified_only?: "true" | "false";
};
export class InvalidCatalogueQuery extends Error {
  constructor() { super("Check your filters. Use a valid category, price range and recent-first ordering."); }
}
const keys = ["q", "category_id", "location", "condition", "min_price", "max_price", "limit", "sort", "verified_only", "cursor"] as const;
export function parseCatalogueQuery(raw: SearchParameters): { query: CatalogueQuery; category?: string } {
  const query: CatalogueQuery = {};
  for (const [key, value] of Object.entries(raw)) {
    if (value === undefined) continue;
    if (Array.isArray(value) || (!keys.includes(key as typeof keys[number]) && key !== "category")) throw new InvalidCatalogueQuery();
  }
  for (const key of keys) {
    const value = raw[key] as string | undefined;
    if (value === undefined || value === "") continue;
    if (key === "q" || key === "location") {
      if (/[^\P{C}\r\n\t]/u.test(value)) throw new InvalidCatalogueQuery();
      const text = value.normalize("NFC").trim().replace(/\s+/g, " ");
      if (!text) continue;
      if ([...text].length > 100 || /\p{C}/u.test(text)) throw new InvalidCatalogueQuery();
      query[key] = text;
    } else {
      if (key === "category_id" && !resourceId.safeParse(value).success ||
          key === "condition" && !Object.hasOwn(conditions, value) ||
          (key === "min_price" || key === "max_price") && (!/^\d+(?:\.\d{1,2})?$/.test(value) || value.length > 30 || Number(value) >= 1e12) ||
          key === "cursor" && !cursorSchema.safeParse(value).success ||
          key === "limit" && (!/^\d{1,2}$/.test(value) || Number(value) < 1 || Number(value) > 20) ||
          key === "verified_only" && value !== "true" && value !== "false" ||
          key === "sort" && value !== "recent") throw new InvalidCatalogueQuery();
      Object.assign(query, { [key]: value });
    }
  }
  if (query.min_price && query.max_price && Number(query.min_price) > Number(query.max_price)) throw new InvalidCatalogueQuery();
  const category = raw.category as string | undefined;
  if (category && (query.category_id || category.length > 120)) throw new InvalidCatalogueQuery();
  return { query, ...(category ? { category } : {}) };
}
export function resolveCategory(query: CatalogueQuery, label: string | undefined, categories: CatalogueCategory[]): CatalogueQuery {
  if (!label) return query;
  const matches = categories.filter(category => [category.name, category.slug].some(value => value.toLowerCase() === label.trim().toLowerCase()));
  if (matches.length !== 1) throw new InvalidCatalogueQuery();
  return { ...query, category_id: matches[0].id };
}
export function catalogueParameters(query: CatalogueQuery): URLSearchParams {
  const params = new URLSearchParams();
  for (const key of keys) if (query[key]) params.set(key, query[key]);
  return params;
}
export function catalogueHref(query: CatalogueQuery = {}): string {
  const params = catalogueParameters(query).toString();
  return `/marketplace${params ? `?${params}` : ""}`;
}
export function listingHref(id: string, query: CatalogueQuery): string {
  return `/listings/${id}?${new URLSearchParams({ returnTo: catalogueHref(query) })}`;
}
export function safeCatalogueReturn(value: string | string[] | undefined): string {
  if (typeof value !== "string" || value.length > 2048 || /[\x00-\x20\\]/.test(value)) return "/marketplace";
  try {
    const url = new URL(value, "https://catalogue.invalid");
    if (!value.startsWith("/marketplace") || url.origin !== "https://catalogue.invalid" || url.pathname !== "/marketplace" || url.hash) return "/marketplace";
    const raw: SearchParameters = {};
    for (const key of url.searchParams.keys()) {
      const values = url.searchParams.getAll(key);
      raw[key] = values.length > 1 ? values : values[0];
    }
    const parsed = parseCatalogueQuery(raw);
    return parsed.category ? "/marketplace" : catalogueHref(parsed.query);
  } catch { return "/marketplace"; }
}
