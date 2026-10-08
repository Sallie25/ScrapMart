import type { ButtonHTMLAttributes } from "react";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "destructive";
  loading?: boolean;
};

export function Button({
  children,
  variant = "primary",
  loading = false,
  disabled = false,
  type = "button",
  className = "",
  ...props
}: ButtonProps) {
  const variantClasses = {
    primary: "bg-primary text-white hover:bg-primary-hover",
    secondary: "bg-secondary text-white hover:bg-primary",
    destructive: "bg-error text-white hover:opacity-90",
  };

  return (
    <button
      type={type}
      className={`rounded-md px-4 py-2 font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ${variantClasses[variant]} ${className}`}
      {...props}
      disabled={loading || disabled}
      aria-busy={loading}
    >
      {loading ? (
  <span className="flex items-center justify-center gap-2">
    <span
      className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent"
      aria-hidden="true"
    />
    <span>Loading...</span>
  </span>
) : (
  children
)}
    </button>
  );
}