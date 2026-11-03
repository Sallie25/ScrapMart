import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import ts from "typescript";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

// Compile the isolated presentation component in memory with installed tools.
// No network, files generated, session simulation or test-only app route.
const require = createRequire(import.meta.url);
const source = await readFile(
  new URL("../src/components/buyer/buyer-orders.tsx", import.meta.url),
  "utf8",
);
const compiled = ts
  .transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX },
  })
  .outputText.replaceAll(
    '"react/jsx-runtime"',
    JSON.stringify(pathToFileURL(require.resolve("react/jsx-runtime")).href),
  );
const { BuyerOrders } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`
);
const render = (state) =>
  renderToStaticMarkup(createElement(BuyerOrders, { state }));

test("unavailable, loading and failed requests never claim an empty history", () => {
  for (const status of ["unavailable", "loading", "error"]) {
    const html = render({ status });
    assert.doesNotMatch(html, /No orders yet|Your orders<|<button|<a\s/);
    assert.match(html, /My Orders/);
  }
  assert.match(render({ status: "loading" }), /role="status"/);
  assert.match(render({ status: "error" }), /role="alert"/);
});

test("a successful zero-order result renders the responsive empty-cart state", () => {
  const html = render({ status: "success", orders: [] });
  assert.match(html, /No orders yet/);
  assert.match(html, /<svg[^>]*aria-hidden="true"/);
  assert.doesNotMatch(
    html,
    /Browse marketplace|Back to overview|Buyer login preview/,
  );
});

test("populated success renders only the supplied order details", () => {
  // Test data never enters an application route or presentation inventory.
  const html = render({
    status: "success",
    orders: [
      {
        id: "test-only-reference",
        status: "preparing",
        currency: "NGN",
        vendor_business_name: "Test-only vendor",
        total_amount: "1250.00",
        payment_method: "pay_on_delivery",
        created_at: "2026-01-01T12:00:00Z",
        item: {
          title: "Test-only material",
          quantity: "2.000",
          quantity_unit: "kilograms",
        },
      },
    ],
  });
  for (const detail of [
    "test-only-reference",
    "Test-only material",
    "Test-only vendor",
    "preparing",
    "2.000 kilograms",
    "1,250.00",
    "pay on delivery",
  ])
    assert.ok(html.includes(detail), detail);
  assert.doesNotMatch(html, /No orders yet|Orders are not connected/);
  assert.equal((html.match(/<li\b/g) ?? []).length, 1);
});
