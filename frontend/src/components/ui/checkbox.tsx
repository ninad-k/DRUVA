import * as React from "react";
import { Check } from "lucide-react";
import { cn } from "@/utils/cn";

export interface CheckboxProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> {
  checked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
}

export const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
  ({ className, checked, onCheckedChange, ...props }, ref) => (
    <label
      className={cn(
        "relative inline-flex h-4 w-4 shrink-0 cursor-pointer items-center justify-center rounded border border-border bg-background ring-offset-background focus-within:ring-2 focus-within:ring-ring",
        checked && "bg-primary text-primary-foreground border-primary",
        className,
      )}
    >
      <input
        ref={ref}
        type="checkbox"
        className="absolute inset-0 cursor-pointer opacity-0"
        checked={checked}
        onChange={(e) => onCheckedChange?.(e.target.checked)}
        {...props}
      />
      {checked && <Check className="h-3 w-3" />}
    </label>
  ),
);
Checkbox.displayName = "Checkbox";
