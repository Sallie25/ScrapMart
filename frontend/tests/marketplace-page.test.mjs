import test from 'node:test';
import assert from 'node:assert/strict';
import { loadMarketplace } from '../src/lib/server/marketplace/page-data.ts';
import { MarketplaceError } from '../src/lib/server/marketplace/client.ts';
import { catalogueHref } from '../src/lib/marketplace/query.ts';
const id = '11111111-1111-4111-8111-111111111111';
const category = { id, name: 'Metals', slug: 'metals' };
const cursor = 'YWJj';
const empty = { listings: [], next_cursor: null };
const fake = (categories, search) => () => ({ categories, search });

test('category labels become real IDs and all filters reach search', async () => {
  const raw = { category: 'metals', q: ' copper ', location: 'Ikeja', condition: 'used', min_price: '10', max_price: '20', limit: '2' };
  let sent;
  const result = await loadMarketplace(raw, fake(async () => [category], async query => { sent = query; return empty; }));
  assert.deepEqual(result.page, empty);
  assert.deepEqual(sent, { category_id: id, q: 'copper', location: 'Ikeja', condition: 'used', min_price: '10', max_price: '20', limit: '2' });
});

test('empty catalogue stays empty, with no demo substitution', async () => {
  const result = await loadMarketplace({}, fake(async () => [category], async () => empty));
  assert.deepEqual(result.page, empty);
  assert.equal(result.error, undefined);
});

test('category, listing and query failures are distinct and never expose a page', async () => {
  const broken = async () => { throw new Error('down'); };
  for (const [raw, make, expected] of [
    [{ sort: 'price_low' }, () => assert.fail('Invalid query reached API'), 'filters'],
    [{ category: 'missing' }, fake(async () => [category], () => assert.fail('Unknown category reached search')), 'filters'],
    [{}, fake(broken, () => assert.fail('Category failure reached search')), 'categories'],
    [{}, fake(async () => [category], broken), 'listings'],
    [{}, fake(async () => [category], async () => { throw new MarketplaceError('invalid_query'); }), 'filters'],
  ]) {
    const result = await loadMarketplace(raw, make);
    assert.equal(result.error, expected);
    assert.equal(result.page, undefined);
  }
});

test('cursor pagination preserves filters and forwards opaque token', async () => {
  const query = { q: 'copper', category_id: id, location: 'Ikeja', condition: 'used', min_price: '5', limit: '2', cursor };
  let sent;
  const result = await loadMarketplace(query, fake(async () => [category], async value => { sent = value; return { listings: [], next_cursor: 'bmV4dA' }; }));
  assert.deepEqual(sent, query);
  const href = catalogueHref({ ...result.query, cursor: result.page.next_cursor });
  const params = new URL(href, 'https://test.invalid').searchParams;
  for (const [key, value] of Object.entries({ ...query, cursor: 'bmV4dA' })) assert.equal(params.get(key), value);
});
