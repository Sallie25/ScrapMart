import type { InputHTMLAttributes } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function AuthField({
  label,
  error,
  helper,
  id,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & {
  id: string;
  label: string;
  error?: string;
  helper?: string;
}) {
  return (
    <div>
      <Label htmlFor={id} required={props.required}>
        {label}
      </Label>
      <Input
        {...props}
        id={id}
        error={Boolean(error)}
        aria-invalid={Boolean(error)}
        aria-describedby={
          [error ? `${id}-error` : null, helper ? `${id}-helper` : null]
            .filter(Boolean)
            .join(" ") || undefined
        }
      />
      {helper && (
        <p
          id={`${id}-helper`}
          className="auth-helper mt-2 text-xs leading-relaxed"
        >
          {helper}
        </p>
      )}
      {error && (
        <p
          id={`${id}-error`}
          role="alert"
          className="mt-2 text-sm text-red-700"
        >
          {error}
        </p>
      )}
    </div>
  );
}
