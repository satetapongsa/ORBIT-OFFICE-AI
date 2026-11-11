import { useId, type ComponentProps } from "react";
import type { FieldError, UseFormRegisterReturn } from "react-hook-form";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface FormFieldProps extends Omit<ComponentProps<typeof Input>, "id"> {
  label: string;
  registration: UseFormRegisterReturn;
  error?: FieldError;
  hint?: string;
}

/** Label + input + accessible error/hint text, wired for React Hook Form. */
export function FormField({ label, registration, error, hint, ...inputProps }: FormFieldProps) {
  const id = useId();
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        {...inputProps}
        {...registration}
      />
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-destructive text-xs">
          {error.message}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-muted-foreground text-xs">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
