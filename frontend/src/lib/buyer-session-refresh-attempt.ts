const key = "scrapmart:buyer-session-refresh-attempt";

type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export function claimBuyerSessionRefreshAttempt(storage: StorageLike): boolean {
  if (storage.getItem(key) === "1") return false;
  storage.setItem(key, "1");
  return true;
}

export function clearBuyerSessionRefreshAttempt(storage: StorageLike): void {
  storage.removeItem(key);
}
