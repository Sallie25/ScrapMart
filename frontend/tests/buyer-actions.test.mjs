import test from "node:test";
import assert from "node:assert/strict";
import {
  safeListingReturn,
  buyerActionLogin,
} from "../src/lib/marketplace/buyer-actions.ts";

test("buyer actions preserve a listing intent without executing it", () => {
  for (const action of ["contact", "order"]) {
    const url = new URL(
      buyerActionLogin("demo-copper-wire", action),
      "https://scrapmart.example",
    );
    assert.equal(url.pathname, "/login");
    assert.equal(url.searchParams.get("role"), "buyer");
    assert.equal(
      safeListingReturn(url.searchParams.get("returnTo")),
      `/listings/demo-copper-wire?intent=${action}`,
    );
  }
});
test("return destinations reject external URLs and unrecognized paths or actions", () => {
  for (const input of [
    undefined,
    [],
    "https://evil.example",
    "//evil.example",
    "/\\evil.example",
    "/listings/%2f%2fevil?intent=order",
    "/listings/demo?intent=delete",
    "/listings/demo?intent=order&next=https://evil.example",
    "/buyer/dashboard",
    "/listings/demo?intent=order\n",
    "/listings/demo?intent=order#fragment",
    "/listings/demo\n?intent=order",
  ])
    assert.equal(safeListingReturn(input), null);
  assert.equal(buyerActionLogin("../escape", "order"), "/login?role=buyer");
});
