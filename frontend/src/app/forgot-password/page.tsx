import { AuthShell, AuthBack } from "@/components/auth/auth-shell";
import { RecoveryForm } from "@/components/auth/recovery-form";

export default async function ForgotPasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ role?: string }>;
}) {
  const { role: requestedRole } = await searchParams;
  const role = requestedRole === "vendor" ? "vendor" : "buyer";
  return (
    <AuthShell>
      <section className="auth-panel mx-auto max-w-md rounded-3xl p-7 md:p-9">
        <AuthBack href={`/login?role=${role}`}>Back to login</AuthBack>
        <p className="auth-eyebrow">Account help</p>
        <h1 className="auth-title">Reset password</h1>
        <p className="auth-muted mt-2 text-sm">
          Enter your email address to preview password recovery.
        </p>
        <RecoveryForm />
      </section>
    </AuthShell>
  );
}
