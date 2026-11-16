import 'server-only';
import { z } from 'zod';
import { buyerSignupSchema, loginSchema } from '../../validations/auth';

export type Role = 'buyer' | 'vendor';
const pythonSpace = '\t\n\v\f\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000';
const validText = (value: string) => !value.includes('\0') && !/[\uD800-\uDFFF]/u.test(value);
const text = (max: number) => z.string().refine(validText)
  .refine(value => [...value].length >= 1 && [...value].length <= max)
  .refine(value => ![...value].every(character => pythonSpace.includes(character)));
// Shape/ASCII checks only. FastAPI remains authoritative for email-validator,
// IDNA and the versioned collision registry; no DNS or account linking here.
const email = z.string().refine(value => [...value].every(c => c.charCodeAt(0) < 128))
  .transform(value => value.replace(/^[ \t\r\n\v\f]+|[ \t\r\n\v\f]+$/g, '').toLowerCase())
  .refine(value => value.length >= 3 && value.length <= 255 &&
    [...value].every(c => c.charCodeAt(0) >= 33 && c.charCodeAt(0) <= 126) &&
    value.split('@').length === 2 && !value.startsWith('@') && !value.endsWith('@'));
export const buyerRegistration = z.object({ email, password: buyerSignupSchema.shape.password,
  full_name: text(150), phone_number: text(20).nullable().optional() }).strict();
export const vendorRegistration = buyerRegistration.extend({ business_name: text(200) }).strict();
export const vendorEnrollment = z.object({
  business_name: text(200),
  current_password: loginSchema.shape.password,
}).strict();
export const login = z.object({ email, password: loginSchema.shape.password }).strict();
export const acknowledgment = 'If registration was successful, you can now sign in.';
export const verificationStatus = z.enum(['pending', 'approved', 'rejected', 'suspended']);
export const capabilities = z.object({ buyer: z.boolean(), vendor: z.boolean(),
  vendor_verification_status: verificationStatus.nullable() }).strict()
  .refine(value => value.vendor === (value.vendor_verification_status !== null));
export const vendorProfile = z.object({ business_name: z.string(), verification_status: verificationStatus,
  full_name: z.string(), email: z.string(), phone_number: z.string().nullable(),
  created_at: z.string().refine(value => Number.isFinite(Date.parse(value))) }).strict();
export const tokenResponse = z.object({ access_token: z.string().min(1).max(16384)
  .regex(/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/),
  token_type: z.literal('bearer'), expires_in: z.number().int().min(1).max(900) }).strict();
export const safeFields = ['email', 'password', 'full_name', 'phone_number', 'business_name'];
