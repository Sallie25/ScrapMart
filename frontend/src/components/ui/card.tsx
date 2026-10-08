
import type { HTMLAttributes } from "react";

type CardProps = HTMLAttributes<HTMLDivElement> & {
  padding?: "none" | "sm" | "md" | "lg";
  variant?: "default" | "outlined";
};

export function Card({
  children,
  padding = "md",
  variant = "default",
  className = "",
  ...props
}: CardProps) {
  const paddingClasses = {
    none: "",
    sm: "p-3",
    md: "p-5",
    lg: "p-8",
  };

  const variantClasses = {
    default: "border border-border shadow-sm",
    outlined: "border border-border",
  };

  return (
    <div
      className={`rounded-xl bg-surface ${paddingClasses[padding]} ${variantClasses[variant]} ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}