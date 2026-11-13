import test from 'node:test';
import assert from 'node:assert/strict';
import { MarketplaceClient, MarketplaceError } from '../src/lib/server/marketplace/client.ts';
import { listingSchema, formatMoney, formatQuantity, priceBasis } from '../src/lib/marketplace/catalogue.ts';
import { parseCatalogueQuery, resolveCategory, catalogueParameters, catalogueHref, listingHref, safeCatalogueReturn, InvalidCatalogueQuery } from '../src/lib/marketplace/query.ts';

// Mirrors MarketplaceService._dto and cursor_encode; synthetic data stays in tests.
const id = '11111111-1111-4111-8111-111111111111';
const secondId = '22222222-2222-4222-8222-222222222222';
const category = { id, name: 'Metals', slug: 'metals' };
const cursor = Buffer.from(JSON.stringify(['2026-01-01T12:00:00+00:00', id])).toString('base64url');
const listing = {
  id, title: 'Copper scrap', description: 'Clean offcuts', category_id: id, category,
  status: 'active', price: '999999999999.99', price_type: 'per_unit', currency: 'NGN',
  is_negotiable: true, quantity: '12.500', available_quantity: '10.250', quantity_unit: 'kilograms',
  condition: 'used', location_summary: 'Ikeja, Lagos', lga: 'Ikeja', area: null,
  latitude: '6.600000', longitude: '3.350000', location_visibility: 'approximate', directions_allowed: false,
  vendor: { business_name: 'Test vendor', shop_location: 'Ikeja, Lagos', verified: true },
  photos: [{ id, url: `https://photos.example.test/listings/${id}/photo.jpg`, position: 0, width: 800, height: 600 }],
  created_at: '2026-01-01T12:00:00Z', updated_at: '2026-01-01T12:00:00+00:00', published_at: '2026-01-01T12:00:00Z',
};
const json = value => Response.json(value);
const page = (listings = [listing], next_cursor = null) => ({ listings, next_cursor });
const client = transport => new MarketplaceClient('https://api.example.test', transport);
const kind = expected => error => error instanceof MarketplaceError && error.kind === expected;

test('public DTO preserves exact values and strips unadvertised fields', () => {
  const parsed = listingSchema.parse({ ...listing, vendor_id: secondId });
  assert.deepEqual(parsed, listing);
  assert.equal(formatMoney(parsed.price), '₦999,999,999,999.99');
  assert.equal(formatQuantity(parsed.available_quantity), '10.25');
  assert.equal(formatQuantity('10.000'), '10');
  assert.equal(priceBasis(parsed), 'per kilogram');
  assert.equal(priceBasis({ price_type: 'total', quantity_unit: 'pieces' }), 'total lot price');
  for (const change of [{ price: 12.5 }, { quantity_unit: 'kg' }, { condition: 'Mixed' }, { status: 'draft' },
    { vendor: { ...listing.vendor, verified: false } }, { photos: [] }, { category_id: secondId },
    { latitude: '91.000000' }, { photos: [{ ...listing.photos[0], url: 'http://unsafe.test/image.jpg' }] }]) {
    assert.equal(listingSchema.safeParse({ ...listing, ...change }).success, false);
  }
});

test('search normalizes text and serializes every supported filter exactly', () => {
  const { query } = parseCatalogueQuery({ q: '  Cafe\u0301\t copper\n', location: ' Ikeja  Lagos ', category_id: id,
    condition: 'for_parts', min_price: '0000000000001.20', max_price: '999999999999.99', verified_only: 'false', sort: 'recent', limit: '2', cursor });
  assert.equal(query.q, 'Café copper');
  assert.equal(query.location, 'Ikeja Lagos');
  assert.deepEqual(Object.fromEntries(catalogueParameters(query)), query);
  assert.deepEqual(parseCatalogueQuery({ q: ' ', location: '', min_price: '' }), { query: {} });
});

test('invalid filters and duplicate search parameters fail before transport', async () => {
  for (const raw of [{ q: ['one', 'two'] }, { unknown: 'x' }, { q: 'a'.repeat(101) }, { q: 'a\vb' },
    { q: '\u0000' }, { category_id: 'Metals' }, { condition: 'mixed' }, { min_price: '-1' }, { max_price: '1e3' },
    { min_price: '1.001' }, { max_price: '1000000000000' }, { min_price: '0'.repeat(31) },
    { min_price: '2', max_price: '1.99' }, { limit: '0' }, { limit: '21' }, { limit: '1.5' },
    { sort: 'price_asc' }, { verified_only: 'yes' }, { cursor: '../bad' }, { cursor: 'a'.repeat(301) },
    { category: 'Metals', category_id: id }]) {
    assert.throws(() => parseCatalogueQuery(raw), InvalidCatalogueQuery);
    await assert.rejects(client(() => assert.fail('Invalid query reached transport')).search(raw), kind('invalid_query'));
  }
});

test('category labels resolve uniquely and navigation preserves filters and cursor safely', () => {
  assert.deepEqual(resolveCategory({}, ' METALS ', [category]), { category_id: id });
  assert.throws(() => resolveCategory({}, 'unknown', [category]), InvalidCatalogueQuery);
  assert.throws(() => resolveCategory({}, 'metals', [category, { ...category, id: secondId }]), InvalidCatalogueQuery);
  const query = { q: 'copper & wire', category_id: id, cursor, limit: '2', verified_only: 'true' };
  const href = catalogueHref(query);
  assert.equal(safeCatalogueReturn(href), href);
  assert.equal(new URL(listingHref(id, query), 'https://shop.test').searchParams.get('returnTo'), href);
  for (const unsafe of ['https://evil.test/marketplace', '//evil.test/marketplace', '/marketplace/../other',
    '/marketplace#fragment', '/marketplace?q=a&q=b', '/marketplace?category=Metals', '/marketplace?sort=price_asc', ['x']]) {
    assert.equal(safeCatalogueReturn(unsafe), '/marketplace');
  }
});

test('public GET requests omit credentials and disable caching and redirects', async () => {
  const api = client(async request => {
    const url = new URL(request.url);
    assert.equal(url.pathname, '/api/v1/listings');
    assert.equal(url.searchParams.get('q'), 'copper & wire');
    assert.equal(request.method, 'GET');
    assert.equal(request.credentials, 'omit');
    assert.equal(request.redirect, 'error');
    assert.equal(request.cache, 'no-store');
    assert.deepEqual([...request.headers], [['accept', 'application/json']]);
    return json(page());
  });
  assert.deepEqual(await api.search({ q: 'copper & wire', limit: '' }), page());
});

test('listing pagination round-trips opaque cursors including empty intermediate pages', async () => {
  const requests = [];
  const api = client(async request => {
    requests.push(new URL(request.url));
    return json(requests.length === 1 ? page([], cursor) : page());
  });
  const first = await api.search({ limit: '1', condition: 'used' });
  assert.deepEqual(first, page([], cursor));
  assert.deepEqual(await api.search({ limit: '1', condition: 'used', cursor: first.next_cursor }), page());
  assert.equal(requests[1].searchParams.get('cursor'), cursor);
  assert.equal(requests[1].searchParams.get('condition'), 'used');
  for (const [payload, query] of [[page([listing, listing]), {}], [page([listing, { ...listing, id: secondId }]), { limit: '1' }], [page([], cursor), { cursor }]]) {
    await assert.rejects(client(async () => json(payload)).search(query), kind('invalid_response'));
  }
});

test('categories follow after pagination and reject duplicate or looping results', async () => {
  let calls = 0;
  const api = client(async request => {
    const url = new URL(request.url);
    assert.equal(url.pathname, '/api/v1/categories');
    assert.equal(url.searchParams.get('limit'), '100');
    assert.equal(url.searchParams.get('after'), calls ? id : null);
    return json(calls++ ? { categories: [{ ...category, id: secondId }], next_cursor: null } : { categories: [category], next_cursor: id });
  });
  assert.equal((await api.categories()).length, 2);
  await assert.rejects(client(async () => json({ categories: [category], next_cursor: id })).categories(), kind('invalid_response'));
  await assert.rejects(client(async () => json({ categories: [], next_cursor: id })).categories(), kind('invalid_response'));
  assert.deepEqual(await client(async () => json({ categories: [], next_cursor: null })).categories(), []);
});

test('detail validates identifiers, identity and unavailable-item status', async () => {
  await assert.rejects(client(() => assert.fail('Invalid identifier reached transport')).listing('demo-1'), kind('not_found'));
  assert.deepEqual(await client(async request => {
    assert.equal(new URL(request.url).pathname, `/api/v1/listings/${id}`);
    return json(listing);
  }).listing(id), listing);
  await assert.rejects(client(async () => json({ ...listing, id: secondId })).listing(id), kind('invalid_response'));
  await assert.rejects(client(async () => new Response(null, { status: 404 })).listing(id), kind('not_found'));
});

test('configuration, transport, HTTP and malformed responses have explicit error kinds', async () => {
  for (const origin of [undefined, '', 'https://api.test/', 'https://user:pass@api.test', 'http://api.test', 'https://api.test/path']) {
    assert.throws(() => new MarketplaceClient(origin), kind('configuration'));
  }
  assert.doesNotThrow(() => new MarketplaceClient('http://localhost:8000'));
  for (const [status, expected] of [[422, 'invalid_query'], [503, 'unavailable'], [404, 'unavailable'], [302, 'unavailable']]) {
    await assert.rejects(client(async () => new Response(null, { status })).search({}), kind(expected));
  }
  await assert.rejects(client(async () => { throw new Error('private diagnostic'); }).search({}), kind('unavailable'));
  for (const response of [new Response('html'), new Response('{', { headers: { 'content-type': 'application/json' } }),
    json({ listings: [] }), json(page([{ ...listing, price: 5 }])),
    new Response('x'.repeat(1024 * 1024 + 1), { headers: { 'content-type': 'application/json' } })]) {
    await assert.rejects(client(async () => response).search({}), kind('invalid_response'));
  }
});

test('timeouts bound both transport and stalled bodies, aborting and cancelling work', async () => {
  let pendingRequest;
  const stalled = new MarketplaceClient('https://api.test', request => {
    pendingRequest = request;
    return new Promise(() => {});
  }, 15);
  await assert.rejects(stalled.search({}), kind('unavailable'));
  assert.equal(pendingRequest.signal.aborted, true);
  let cancelled = false;
  const body = new ReadableStream({ cancel() { cancelled = true; } });
  const slow = new MarketplaceClient('https://api.test', async () => new Response(body, { headers: { 'content-type': 'application/json' } }), 15);
  await assert.rejects(slow.search({}), kind('unavailable'));
  assert.equal(cancelled, true);
});
