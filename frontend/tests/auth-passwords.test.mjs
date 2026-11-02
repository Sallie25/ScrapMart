// Run with Node 22.18+ or Node 24: node --test tests/auth-passwords.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import {
  buyerSignupSchema,
  vendorSignupSchema,
  loginSchema,
} from "../src/lib/validations/auth.ts";

const signupSchemas = [
  buyerSignupSchema.shape.password,
  vendorSignupSchema.shape.password,
];
const loginPassword = loginSchema.shape.password;
const invalidEncoding = [
  "x".repeat(15) + "\u0000",
  "\ud800" + "x".repeat(15),
  "x".repeat(15) + "\udfff",
];

test("buyer and vendor signup enforce the same 15–128 code-point boundaries", () => {
  for (const schema of signupSchemas) {
    for (const length of [0, 1, 14, 129])
      assert.equal(schema.safeParse("a".repeat(length)).success, false);
    for (const length of [15, 16, 127, 128])
      assert.equal(schema.safeParse("a".repeat(length)).success, true);
    assert.equal(schema.safeParse("😀".repeat(14)).success, false);
    assert.equal(schema.safeParse("😀".repeat(128)).success, true);
    assert.equal(schema.safeParse("😀".repeat(129)).success, false);
  }
});

test("signup preserves Unicode and boundary spaces without composition rules", () => {
  const passwords = [
    "  a plain passphrase  ",
    "é".repeat(15),
    "😀".repeat(15),
    "  " + "x".repeat(11) + "  ",
    "\ufeff".repeat(15),
    "e\u0301".repeat(8),
  ];
  for (const schema of signupSchemas)
    for (const password of passwords)
      assert.equal(schema.parse(password), password);
});

test("signup rejects Python whitespace and strict UTF-8 violations", () => {
  const whitespace =
    "\t\n\v\f\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000";
  for (const schema of signupSchemas) {
    for (const character of whitespace)
      assert.equal(schema.safeParse(character.repeat(15)).success, false);
    for (const password of invalidEncoding)
      assert.equal(schema.safeParse(password).success, false);
  }
});

test("login keeps its separate 1–128 boundary and permits existing short/whitespace passwords", () => {
  for (const password of [
    "a",
    " ",
    "\u0085",
    "short password",
    "😀".repeat(128),
    " ".repeat(128),
  ])
    assert.equal(loginPassword.parse(password), password);
  for (const password of [
    "",
    "a".repeat(129),
    "😀".repeat(129),
    ...invalidEncoding,
  ])
    assert.equal(loginPassword.safeParse(password).success, false);
});
