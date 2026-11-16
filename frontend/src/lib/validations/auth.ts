import { z } from "zod";

// Match Python str.isspace(), including U+001C–001F and U+0085, but not U+FEFF.
const passwordWhitespace = new Set(
  "\t\n\v\f\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000",
);

// Match backend security.py/login_schemas.py without trimming or normalization.
// Python counts Unicode code points; JavaScript string.length counts UTF-16 units.
function passwordSchema(minimumLength: 1 | 15, rejectWhitespace: boolean) {
  return z.string().superRefine((password, context) => {
    const characters = [...password];
    if (characters.length < minimumLength || characters.length > 128) {
      context.addIssue({
        code: "custom",
        message:
          minimumLength === 15
            ? "Use 15–128 characters for your password"
            : "Enter a password of 1–128 characters",
      });
    }
    // Unpaired surrogates cannot be encoded as strict UTF-8. The /u flag
    // permits correctly paired astral characters such as emoji.
    if (password.includes("\u0000") || /[\uD800-\uDFFF]/u.test(password)) {
      context.addIssue({
        code: "custom",
        message: "Password contains a null character or invalid Unicode text",
      });
    }
    if (
      rejectWhitespace &&
      characters.length > 0 &&
      characters.every((character) => passwordWhitespace.has(character))
    ) {
      context.addIssue({
        code: "custom",
        message: "Password cannot contain only whitespace",
      });
    }
  });
}

const signupPasswordSchema = passwordSchema(15, true);
// Do not apply signup's minimum or all-whitespace rule to existing credentials.
const loginPasswordSchema = passwordSchema(1, false);

const commonSignupFields = {
  fullName: z.string().trim().min(2, "Enter your full name"),
  email: z.string().trim().email("Enter a valid email address"),
  phone: z.string().trim().min(7, "Enter a valid phone number"),
  password: signupPasswordSchema,
  previewConsent: z
    .boolean()
    .refine(Boolean, "Confirm that you understand this is a demo"),
};
export const buyerSignupSchema = z.object(commonSignupFields);
// Vendor registration requires a business name in the current backend contract.
// Location, address, and identity evidence belong to the later verification flow.
export const vendorSignupSchema = buyerSignupSchema.extend({
  businessName: z.string().trim().min(2, "Enter your shop or business name"),
});
export type BuyerSignupValues = z.infer<typeof buyerSignupSchema>;
export type VendorSignupValues = z.infer<typeof vendorSignupSchema>;
export type SignupFormValues = BuyerSignupValues | VendorSignupValues;
export const loginSchema = z.object({
  email: z.string().trim().email("Enter a valid email address"),
  password: loginPasswordSchema,
});
export type LoginFormValues = z.infer<typeof loginSchema>;
