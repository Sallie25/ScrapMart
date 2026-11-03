# Batch 2D — AI-generated illustrative media

## Provenance

The project owner supplied eight PNGs in `/home/sallieakpan/Desktop/scrapmart-generated-images` and explicitly authorized integration. They report generation specifically for ScrapMart using ChatGPT. These are photorealistic AI illustrations, not photographs, documentary evidence of Nigeria, actual sellers, premises or inventory. No generation model, original prompt or generation date was supplied; none is inferred. No third-party stock or Commons licence is assigned to these generated images.

Actual image contents were inspected in a contact sheet before selection. `public/images/generated/SOURCES.json` records original filenames, hashes, visual contents, derivative paths and byte sizes. Original PNGs are untouched. Derivatives are proportionally resized to 1280px wide and WebP quality 78, metadata removed, with responsive CSS cropping; Next Image supplies responsive sizes and lazy loading.

| Original | Observed content | Used for |
| --- | --- | --- |
| Colourful Clothing Bales and Worn Shoes.png | Compressed clothing and assorted shoes | Clothes category and sample clothing listings |
| Industrial Cardboard Recycling Bales.png | Flattened corrugated cardboard and bales | Cardboard samples; landing fourth slide |
| Recycling Yard with Compressed Plastic Bottles.png | Bags/bales of plastic bottles | Plastics category, bottle/PET sample listings |
| Rusty Steel Scrap Pile in Daylight.png | Rusty beams, pipes and steel sections | Iron category and explicitly iron/steel samples |
| Scrapyard Heap of Electronic Waste.png | Discarded monitors, computer cases, circuit boards | Electronics category and matching samples |
| Shimmering Aluminium Scrap Pile.png | Silvery sections and metal offcuts | Aluminium category and samples |
| Shiny Copper Wires in a Worn Sack.png | Coiled bare copper wire in a sack | Copper category and samples |
| Worn Tyres at the Recycling Yard.png | Stacks of used tyres | Tyre context in landing third slide |

Material identity describes intended illustrative content, not independently tested metal or polymer composition. General mixed metal, machinery, auto parts, engines, motors, batteries, glass, plain paper, loose rubber and unknown materials retain the existing code-native drawings. Tyres are not substituted for loose rubber; cardboard is not substituted for plain paper. The landing fourth slide now explicitly says Cardboard.

## Placement and priority

`MaterialVisual` provides labelled generated material imagery, falling back to `MaterialPlaceholder` when no suitable image exists. Buyer category tiles use the shared renderer. Landing slides 3/4 use it; slides 1/2 retain the verified Nigerian Seme/Enugu photographs and all their credits, source/licence links and contextual labels. Landing category icons remain unchanged to preserve the approved design.

`ListingPhoto` retains browser-upload loading and priority. Only IDs in the existing Buyer presentation fixture collection may receive generated fallback imagery. Locally created/other listing IDs without uploads retain material drawings. Generated images never overwrite stored photos. Uploaded-photo decoding failures retain the existing graceful fallback behavior. Full listing images visibly say “AI illustration · Not seller inventory”; compact images say “AI illustration”, with descriptive alt text identifying generated content rather than an actual location or item.

No fixture data, category links, search, filters, route behavior, authentication, orders, backend or upload storage implementation changed. Vendor sample rows use the same priority-preserving renderer. No new media downloads, packages, video, commits or deployments.

## Validation

- `npm run lint`
- `node node_modules/typescript/bin/tsc --noEmit --incremental false`
- `npm run build -- --webpack`
- Existing material, orders and password tests.
- `git diff --check`
- Local browser regression script: `/tmp/scrapmart-batch2d-check.mjs`.
- Screenshots: `/tmp/scrapmart-batch2d-{landing,marketplace,gallery-copper,categories,vendor}-{desktop,mobile}.png`.

All listed checks passed. Browser coverage: landing, marketplace, copper detail, Buyer category tiles and Vendor dashboard at 320, 390, 768, 1024 and 1440 pixels with no horizontal overflow. Verified both Nigerian photograph/licence links, two generated hero slides, visible AI/non-inventory labels, correct aluminium/copper mapping, engine placeholders, working search/filters, truthful unavailable orders and public marketplace layout. Seeded an isolated test-browser copper photo Blob and confirmed it overrides the AI fallback; removed only that test Blob afterward. No runtime exceptions, failed image requests or API mutations. Marketplace desktop and tyre hero mobile screenshots were visually inspected.

Focused hero screenshots: `/tmp/scrapmart-batch2d-hero-{tyres,cardboard}-{1440,390}.png`. Local preview: `http://localhost:3113`. Original media and both Commons derivatives/attribution records remain unchanged. Working branch: `feature/frontend-buyer-vendor-integration`; all current and earlier batch edits remain uncommitted.
