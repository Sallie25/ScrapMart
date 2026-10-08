
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type FormFieldProps = {
  id: string;
  label: string;
  type?: string;
  placeholder?: string;
  required?: boolean;
  errorMessage?: string;
  helperText?: string;
};

export function FormField({
  id,
  label,
  type = "text",
  placeholder,
  required = false,
  errorMessage,
  helperText,
}: FormFieldProps) {
  const hasError = Boolean(errorMessage);

  return (
    <div className="w-full">
      <Label htmlFor={id} required={required}>
        {label}
      </Label>

      <Input
        id={id}
        name={id}
        type={type}
        placeholder={placeholder}
        required={required}
        error={hasError}
        aria-invalid={hasError}
        aria-describedby={
          hasError
            ? `${id}-error`
            : helperText
              ? `${id}-helper`
              : undefined
        }
      />

      {hasError ? (
        <p
          id={`${id}-error`}
          className="mt-1.5 text-sm text-error"
          role="alert"
        >
          {errorMessage}
        </p>
      ) : helperText ? (
        <p
          id={`${id}-helper`}
          className="mt-1.5 text-sm text-muted"
        >
          {helperText}
        </p>
      ) : null}
    </div>
  );
}