import test from 'node:test';
import assert from 'node:assert/strict';
import { markConfirmedLogout, takeConfirmedLogout } from '../src/lib/logout-feedback.ts';

function storage() {
  const values = new Map();
  return {
    setItem(key, value) { values.set(key, value); },
    getItem(key) { return values.get(key) ?? null; },
    removeItem(key) { values.delete(key); },
  };
}

test('confirmed sign-out feedback is role-specific and shown once', () => {
  const store = storage();
  assert.equal(takeConfirmedLogout('buyer', store), false);
  markConfirmedLogout('buyer', store);
  assert.equal(takeConfirmedLogout('vendor', store), false);
  markConfirmedLogout('vendor', store);
  assert.equal(takeConfirmedLogout('vendor', store), true);
  assert.equal(takeConfirmedLogout('vendor', store), false);
});
