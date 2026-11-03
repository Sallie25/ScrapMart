import test from "node:test";
import assert from "node:assert/strict";
import { getMaterial } from "../src/lib/media/materials.ts";

test("specific listing materials override broad category fallbacks", () => {
  assert.equal(getMaterial("Metals", "Clean Aluminium Scrap"), "aluminium");
  assert.equal(getMaterial("Metals", "Copper Wire Offcuts"), "copper");
  assert.equal(getMaterial("Metals", "Iron and Steel Scrap"), "iron");
  assert.equal(getMaterial("Paper", "Used Cardboard Bundles"), "cardboard");
  assert.equal(getMaterial("Machinery", "Used Generator Engine"), "engine");
  assert.equal(getMaterial("Electronics", "Faulty Electric Motors"), "motor");
});

test("category illustrations distinguish materials previously shown incorrectly", () => {
  for (const [category, expected] of [
    ["Plastics", "plastics"],
    ["Electronics", "electronics"],
    ["Batteries", "batteries"],
    ["Copper", "copper"],
    ["Aluminum", "aluminium"],
    ["Tyres", "tyres"],
    ["Rubber", "rubber"],
    ["Paper", "paper"],
    ["Cardboard", "cardboard"],
    ["PET bottles", "bottles"],
    ["Other", "other"],
  ])
    assert.equal(getMaterial(category), expected, category);
});
