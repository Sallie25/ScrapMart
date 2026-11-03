# Batch 2A — truthful material imagery

No photographs were downloaded, generated, replaced on disk or cleared for reuse in this batch. Existing photo files and listing records remain unchanged. Batch 1 public layout, Explore navigation and truthful orders states are preserved.

Uncleared presentation photos are no longer rendered. Shared code-native SVG material illustrations explicitly say “Illustration · Photo unavailable” (compact tiles say “Illustration”). These drawings are not documentary photographs, Nigerian-location evidence or seller inventory evidence. No third-party photo licence is claimed for them.

## Rendering changes

- Landing: retains four rotating frames, pause/dots, responsive geometry and the approved styling; subjects are plastics/PET, metals, tyres/rubber, and paper/cardboard illustrations. No video or geographical photo claims.
- Buyer and legacy marketplace cards: category-wide metal/photo fallbacks are replaced with title-aware material drawings. Copper, aluminium, ferrous scrap, paper/cardboard and other materials are distinct.
- Categories: existing labels, links and filters remain; batteries no longer illustrate Plastics or Electronics.
- Details: one actual uploaded photo, or one labelled material placeholder. Unrelated repair images and repeated gallery padding are removed. No invented alternate views or gallery controls for nonexistent images.
- Vendor overview, inventory and bulk review: shared renderer replaces sample photos; bulk copy now accurately describes sample illustrations.

## Uploaded-photo priority

`ListingPhoto` reads the existing browser-local IndexedDB photo by listing ID before displaying any illustration. An uploaded image is labelled “Uploaded photo.” Placeholder fallback covers absent, unreadable and undecodable images without deleting stored data or showing a broken-image icon. A listing ID change cannot display a previous listing's upload. The existing upload/save/delete and photo cleanup services are unchanged. No remote seller photo integration is added or implied.

## Retained source records

`public/images/buyer/SOURCES.json` and `docs/figma-source-mapping.md` remain historical records of the designer export, not permission clearance or current presentation-image configuration. Those image paths remain in fixtures solely to preserve existing data. Any future photo introduction needs asset-specific source, rights, relevance and location checks. No unverified photo should replace an upload or be represented as a seller's stock.

## Verification

Passed lint, explicit TypeScript (`tsc --noEmit --incremental false`), Webpack production build, material-selection tests, Buyer order-state tests, password tests and diff check. Browser checks passed at 320/390/768/1024/1440px for Marketplace, category tiles, Copper/Aluminium details and Vendor overview. Vendor inventory/bulk placeholders, search/filters, Batch 1 behavior, uploaded-photo precedence over fixture paths, and missing/undecodable upload fallback passed. No runtime exceptions, failed photo requests or API mutations were observed. Listing data and `public/images/` have no changes.

Review screenshots: `/tmp/scrapmart-batch2a-marketplace-{desktop,mobile}.png`, `/tmp/scrapmart-batch2a-category-tiles-{desktop,mobile}.png`, `/tmp/scrapmart-batch2a-gallery-{copper,aluminium}-{desktop,mobile}.png`.
