import "server-only";
import { InvalidCatalogueQuery, parseCatalogueQuery, resolveCategory } from "../../marketplace/query";
import type { SearchParameters } from "../../marketplace/query";
import { MarketplaceError } from "./client";
import type { MarketplaceClient } from "./client";
import type { CatalogueCategory, ListingPage } from "../../marketplace/catalogue";
import type { CatalogueQuery } from "../../marketplace/query";

export type MarketplaceView = { categories: CatalogueCategory[]; query: CatalogueQuery; page?: ListingPage; error?: "filters" | "categories" | "listings" };
export async function loadMarketplace(raw: SearchParameters, makeClient: () => Pick<MarketplaceClient, "categories" | "search">): Promise<MarketplaceView> {
  const view: MarketplaceView = { categories: [], query: {} };
  try {
    const parsed = parseCatalogueQuery(raw);
    view.query = parsed.query;
    const client = makeClient();
    try { view.categories = await client.categories(); }
    catch { view.error = "categories"; }
    if (!view.error) {
      view.query = resolveCategory(parsed.query, parsed.category, view.categories);
      view.page = await client.search(view.query);
    }
  } catch (error) {
    view.error = error instanceof InvalidCatalogueQuery || error instanceof MarketplaceError && error.kind === "invalid_query" ? "filters" : "listings";
  }
  return view;
}
