import test from 'node:test';
import assert from 'node:assert/strict';
import { claimBuyerSessionRefreshAttempt, clearBuyerSessionRefreshAttempt } from '../src/lib/buyer-session-refresh-attempt.ts';

test('one refresh attempt is allowed until a confirmed dashboard session clears the guard', () => {
  const values = new Map();
  const storage = {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key),
  };
  assert.equal(claimBuyerSessionRefreshAttempt(storage), true);
  assert.equal(claimBuyerSessionRefreshAttempt(storage), false);
  clearBuyerSessionRefreshAttempt(storage);
  assert.equal(claimBuyerSessionRefreshAttempt(storage), true);
});
