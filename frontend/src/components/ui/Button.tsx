"use client";

import { ButtonHTMLAttributes, forwardRef } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost";
type Size = "md" | "sm" | "icon";

const base =
  "inline-flex items-center justify-center gap-2 rounded-[var(--radius-md)] font-medium transition-all duration-150 active:scale-[0.97] disabled:opacity-50 disabled:pointer-events-none disabled:active:scale-100";

const variants: Record<Variant, string> = {
  primary: "bg-accent text-accent-foreground shadow-[var(--shadow-sm)] hover:bg-accent-hover",
  secondary: "border border-border bg-surface text-foreground hover:bg-surface-muted",
  danger: "border border-danger/30 text-danger hover:bg-danger-soft",
  ghost: "text-foreground hover:bg-surface-muted",
};

const sizes: Record<Size, string> = {
  md: "px-4 py-2.5 text-sm",
  sm: "px-3 py-1.5 text-[13px]",
  icon: "h-9 w-9 shrink-0 p-0",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", size = "md", className = "", ...props }, ref) => (
    <button
      ref={ref}
      className={`${base} ${variants[variant]} ${sizes[size]} ${className}`}
      {...props}
    />
  )
);
Button.displayName = "Button";
