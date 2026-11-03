import "server-only";
import { z } from "zod";
import { categoryPageSchema, listingPageSchema, listingSchema, resourceId } from "../../marketplace/catalogue";
import { catalogueParameters, InvalidCatalogueQuery, parseCatalogueQuery } from "../../marketplace/query";
import type { CatalogueCategory } from "../../marketplace/catalogue";
import type { CatalogueQuery } from "../../marketplace/query";

type Failure = "configuration" | "unavailable" | "invalid_response" | "invalid_query" | "not_found";
export class MarketplaceError extends Error {
  readonly kind: Failure;
  constructor(kind: Failure) { super("Marketplace request could not be completed"); this.kind = kind; }
}
type Transport = (request: Request) => Promise<Response>;
function apiOrigin(value: string | undefined): string {
  try {
    if (!value || value !== value.trim()) throw new Error();
    const url = new URL(value);
    const local = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
    if (url.origin !== value || url.username || url.password ||
      !(url.protocol === "https:" || url.protocol === "http:" && local)) throw new Error();
    return url.origin;
  } catch { throw new MarketplaceError("configuration"); }
}

export class MarketplaceClient {
  private readonly origin: string;
  private readonly transport: Transport;
  private readonly timeoutMs: number;
  constructor(origin: string | undefined, transport: Transport = request => fetch(request), timeoutMs = 8000) {
    this.origin = apiOrigin(origin); this.transport = transport; this.timeoutMs = timeoutMs;
  }
  private async get<T>(path: string, schema: z.ZodType<T>, detail = false): Promise<T> {
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      return await Promise.race([
        new Promise<never>((_, reject) => { timer = setTimeout(() => {
          abort.abort(); reject(new MarketplaceError("unavailable"));
        }, this.timeoutMs); }),
        (async () => {
          const response = await this.transport(new Request(`${this.origin}/api/v1${path}`, {
            method: "GET", headers: { Accept: "application/json" }, credentials: "omit",
            redirect: "error", cache: "no-store", signal: abort.signal,
          }));
          if (response.status !== 200) {
            void response.body?.cancel().catch(() => {});
            throw new MarketplaceError(response.status === 404 && detail ? "not_found" : response.status === 422 ? "invalid_query" : "unavailable");
          }
          if (response.headers.get("content-type")?.split(";", 1)[0].trim() !== "application/json" || !response.body) throw new MarketplaceError("invalid_response");
          // Bound both response size and time, including slow/stalled body streams.
          const reader = response.body.getReader();
          const cancel = () => { void reader.cancel().catch(() => {}); };
          abort.signal.addEventListener("abort", cancel, { once: true });
          const chunks: Uint8Array[] = []; let size = 0;
          try {
            while (true) {
              const result = await reader.read();
              if (result.done) break;
              size += result.value.byteLength;
              if (size > 1024 * 1024) throw new MarketplaceError("invalid_response");
              chunks.push(result.value);
            }
          } finally { abort.signal.removeEventListener("abort", cancel); cancel(); }
          const bytes = new Uint8Array(size); let offset = 0;
          for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
          try { return schema.parse(JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes))); }
          catch { throw new MarketplaceError("invalid_response"); }
        })(),
      ]);
    } catch (error) {
      if (error instanceof MarketplaceError) throw error;
      throw new MarketplaceError("unavailable");
    } finally { clearTimeout(timer); abort.abort(); }
  }
  async categories(): Promise<CatalogueCategory[]> {
    const result: CatalogueCategory[] = []; const cursors = new Set<string>(); const ids = new Set<string>();
    let after: string | null = null;
    for (let page = 0; page < 20; page++) {
      const data: z.infer<typeof categoryPageSchema> = await this.get(`/categories?${new URLSearchParams({ limit: "100", ...(after ? { after } : {}) })}`, categoryPageSchema);
      for (const category of data.categories) {
        if (ids.has(category.id)) throw new MarketplaceError("invalid_response");
        ids.add(category.id); result.push(category);
      }
      if (!data.next_cursor) return result;
      if (!data.categories.length || cursors.has(data.next_cursor)) throw new MarketplaceError("invalid_response");
      after = data.next_cursor; cursors.add(after);
    }
    throw new MarketplaceError("invalid_response"); // Never silently truncate category navigation.
  }
  async search(query: CatalogueQuery) {
    let parsed: CatalogueQuery;
    try { parsed = parseCatalogueQuery(query).query; }
    catch (error) {
      if (error instanceof InvalidCatalogueQuery) throw new MarketplaceError("invalid_query");
      throw error;
    }
    const data = await this.get(`/listings?${catalogueParameters(parsed)}`, listingPageSchema);
    if (data.listings.length > Number(parsed.limit ?? 20) || data.next_cursor && data.next_cursor === parsed.cursor ||
      new Set(data.listings.map(listing => listing.id)).size !== data.listings.length) throw new MarketplaceError("invalid_response");
    return data;
  }
  async listing(id: string) {
    if (!resourceId.safeParse(id).success) throw new MarketplaceError("not_found");
    const listing = await this.get(`/listings/${id}`, listingSchema, true);
    if (listing.id !== id) throw new MarketplaceError("invalid_response");
    return listing;
  }
}
export function marketplaceClient(): MarketplaceClient {
  return new MarketplaceClient(process.env.MARKETPLACE_API_ORIGIN);
}
