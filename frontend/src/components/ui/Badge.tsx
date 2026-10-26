import { ReactNode } from "react";

export function Badge({
  children,
  tone = "default",
}: {
  children: ReactNode;
  tone?: "default" | "accent" | "danger" | "success";
}) {
  const toneClass =
    tone === "accent"
      ? "bg-accent-soft text-accent ring-1 ring-inset ring-accent/15"
      : tone === "danger"
        ? "bg-danger-soft text-danger ring-1 ring-inset ring-danger/15"
        : tone === "success"
          ? "bg-success/10 text-success ring-1 ring-inset ring-success/15"
          : "bg-surface-muted text-muted ring-1 ring-inset ring-border";
  return (
    <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium tracking-wide ${toneClass}`}>
      {children}
    </span>
  );
}
