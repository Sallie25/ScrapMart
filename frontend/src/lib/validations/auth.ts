
import { z } from "zod";

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