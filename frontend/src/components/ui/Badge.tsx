import { ReactNode } from "react";

export function Badge({ children, tone = "default" }: { children: ReactNode; tone?: "default" | "accent" | "danger" }) {
  const toneClass =
    tone === "accent"
      ? "bg-accent text-accent-foreground"
      : tone === "danger"
        ? "bg-danger text-white"
        : "bg-surface-muted text-muted";
  return (
    <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ${toneClass}`}>
      {children}
    </span>
  );
}
