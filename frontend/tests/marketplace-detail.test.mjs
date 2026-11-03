import test from 'node:test';
import assert from 'node:assert/strict';
import { publicLocation } from '../src/lib/marketplace/detail.ts';
import { listingHref, safeCatalogueReturn } from '../src/lib/marketplace/query.ts';
import { MarketplaceClient, MarketplaceError } from '../src/lib/server/marketplace/client.ts';

const id = '11111111-1111-4111-8111-111111111111';
const location = { location_summary: 'Ikeja area', location_visibility: 'approximate', directions_allowed: false, latitude: '6.600000', longitude: '3.350000' };

test('approximate locations never expose coordinate-based directions', () => {
  assert.deepEqual(publicLocation(location), { summary: 'Ikeja area', directionsUrl: null });
  assert.equal(publicLocation({ ...location, directions_allowed: true }).directionsUrl, null);
  assert.equal(publicLocation({ ...location, location_visibility: 'public_site' }).directionsUrl, null);
});

test('public-site directions require both disclosure and explicit permission', () => {
  const result = publicLocation({ ...location, location_visibility: 'public_site', directions_allowed: true });
  assert.equal(result.summary, 'Ikeja area');
  const url = new URL(result.directionsUrl);
  assert.equal(url.protocol, 'https:');
  assert.equal(url.searchParams.get('query'), '6.600000,3.350000');
});

test('real detail links preserve a safe filtered return route', () => {
  const query = { category_id: id, q: 'copper & wire', cursor: 'YWJj' };
  const url = new URL(listingHref(id, query), 'https://shop.invalid');
  assert.equal(url.pathname, `/listings/${id}`);
  assert.equal(safeCatalogueReturn(url.searchParams.get('returnTo')), '/marketplace?q=copper+%26+wire&category_id=11111111-1111-4111-8111-111111111111&cursor=YWJj');
});

test('public detail rejects missing items and invalid backend payloads without fallback', async () => {
  const missing = new MarketplaceClient('https://api.example.test', async () => new Response(null, { status: 404 }));
  await assert.rejects(missing.listing(id), error => error instanceof MarketplaceError && error.kind === 'not_found');
  const malformed = new MarketplaceClient('https://api.example.test', async () => Response.json({ id, title: 'Demo data cannot substitute' }));
  await assert.rejects(malformed.listing(id), error => error instanceof MarketplaceError && error.kind === 'invalid_response');
});
