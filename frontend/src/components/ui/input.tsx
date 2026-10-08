import type { InputHTMLAttributes } from "react";

type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  error?: boolean;
};

export function Input({
  error = false,
  className = "",
  ...props
}: InputProps) {
  return (
    <input
      className={`w-full rounded-md border bg-surface px-3 py-2 text-text placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ${
        error
          ? "border-error focus:ring-error"
          : "border-border"
      } ${className}`}
      {...props}
    />
  );
}