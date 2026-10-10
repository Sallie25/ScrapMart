
import { z } from "zod";

const commonSignupFields = {
  fullName: z
    .string()
    .trim()
    .min(2, "Enter your full name"),

  email: z
    .string()
    .trim()
    .email("Enter a valid email address"),

  phone: z
    .string()
    .trim()
    .min(7, "Enter a valid phone number"),
};

export const buyerSignupSchema = z.object({
  ...commonSignupFields,
});

export const vendorSignupSchema = z.object({
  ...commonSignupFields,

  businessName: z
    .string()
    .trim()
    .min(2, "Enter your shop or business name"),

  businessAddress: z
    .string()
    .trim()
    .min(5, "Enter a more complete shop location"),
});

export type BuyerSignupValues = z.infer<typeof buyerSignupSchema>;
export type VendorSignupValues = z.infer<typeof vendorSignupSchema>;
export type SignupFormValues = BuyerSignupValues | VendorSignupValues;

export const loginSchema = z.object({
  loginIdentifier: z
    .string()
    .trim()
    .min(1, "Enter your email address or phone number"),

  password: z
    .string()
    .min(1, "Enter your password"),
});

export type LoginFormValues = z.infer<typeof loginSchema>;