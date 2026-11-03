# Batch 2C — Nigerian context photographs

## Verification and selection (2 November 2026)

Opened all four original Wikimedia Commons file pages before retrieval. The Seme page failed in the web reader but was successfully retrieved directly as HTML and inspected. Each page identifies its uploader as creator, records own work and grants CC BY-SA 4.0. Nigerian provenance is source-documented; it is not independent geolocation or verification of any ScrapMart seller.

| Candidate | Creator | Evidence | Decision |
| --- | --- | --- | --- |
| [Bagged plastic bottles in Seme](https://commons.wikimedia.org/wiki/File:Bagged_plastic_bottles_in_Seme.jpg) | Bibiire1 | Caption identifies Seme; South West Nigeria campaign and Agbara category | Used: landing slide 1, bagged plastic collection. Actual image inspected; visibly bagged bottles. Soft original, suitable for context at normal display size. No claim about polymer purity. |
| [Coal Camp Enugu](https://commons.wikimedia.org/wiki/File:Coal_Camp_Enugu.jpg) | Tech.Felix | Caption identifies Enugu; description explicitly identifies South East Nigeria junk yard | Used: landing slide 2, contextual yard. Actual image inspected; mixed vehicle scrap visible, tilted composition retained. Not a grade-specific material or seller photo. |
| [Scrap dealing In South-Western Nigeria 02](https://commons.wikimedia.org/wiki/File:Scrap_dealing_In_South-Western_Nigeria_02.jpg) | Chukwukah | Original description identifies Nigerian scrap collection | Downloaded to temporary review storage and inspected, not added to the application. Portrait, softness, clutter and diffuse subject make it unsuitable for the current carousel crop. |
| [Iron Condemned – Heavy Load Journey](https://commons.wikimedia.org/wiki/File:Iron_Condemned_%E2%80%93_Heavy_Load_Journey.jpg) | Johnnybam | Original description explicitly identifies Nigeria; camera GPS 6.218294, 7.075439 | Not used. Original retrieval timed out part-way; retry failed DNS resolution. Complete image could not be inspected. Partial download remains outside the project in /tmp only. |

## Reuse and attribution

[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) permits sharing and adaptation, including commercially, with attribution, licence links, indication of changes and ShareAlike for adaptations. Both distributed image derivatives are offered under that same licence. Attribution appears on each active photograph with its creator, Wikimedia source link, licence link and resize/display-crop disclosure. No copyright transfer or endorsement is claimed. No model releases were supplied; images document collection context, not testimonials or endorsements. Other rights are not waived by the copyright licence.

`public/images/nigerian-scrap/SOURCES.json` records original file-page and binary URLs, creators, evidence, modifications, checksums and exact output sizes. `LICENSE.txt` supplies reuse terms and the legal-code link. Both records are publicly accessible alongside the WebP files. These image terms do not relicense unrelated application code.

## Implementation

Only `src/components/landing/welcome.tsx` changed in this batch. Existing four-slide geometry, pause/play, navigation, transitions and reduced-motion behavior retained. Hidden slides are inert so inactive credit links cannot receive keyboard focus. Photograph labels explicitly say context photograph and not a seller listing. Tyres/rubber and paper/cardboard retain labelled material drawings. The slide selector labels now use the complete slide title.

Two 1280px-wide WebP derivatives, approximately 56 KB and 191 KB, replace multi-megabyte JPEG delivery; Next Image supplies responsive image sizes and lazy loading. Auto-orientation, proportional resize, compression, metadata removal and responsive display crop only; no retouching or generated content. No hero video, stock agency media, API, authentication, fixture data or seller-upload handling changes. No category or listing photographs substituted: the two cleared scenes do not establish the material identity or condition of any offered item.

## Validation

- ESLint, explicit TypeScript no-emit check, Webpack production build and git diff --check passed.
- Existing password, orders and material test files passed.
- Browser regression script: `/tmp/scrapmart-batch2c-check.mjs`.
- Review preview: `http://localhost:3112`.
- Desktop/mobile screenshots: `/tmp/scrapmart-batch2c-landing-0-1440.png`, `/tmp/scrapmart-batch2c-landing-0-390.png`, `/tmp/scrapmart-batch2c-landing-1-1440.png`, `/tmp/scrapmart-batch2c-landing-1-390.png`.

Earlier Batch 1/2A changes remain uncommitted and preserved. Backend, backend/docs and reference source were not opened or changed. No package installation, commit, push or deployment.

Browser checks passed at 320, 390, 768, 1024 and 1440 pixels for existing routes; both active photograph credits and decoded images passed at 320, 390, 768 and 1440. Search, filters, correct material illustrations, unpadded galleries, Vendor bulk/inventory, public layout, Explore navigation and truthful unavailable-orders state passed. An isolated browser-uploaded test Blob retained priority; missing and undecodable uploads fell back gracefully. No runtime exceptions, failed image requests or API mutations. Final desktop/mobile Enugu hero crops visually inspected; credits remain readable and the approved layout is retained. The first browser run stopped on a test-only DOM serialization mistake; the corrected script completed successfully.
