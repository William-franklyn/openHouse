import { ReactNode } from "react";

/** Pure CSS tooltip (group-hover/focus-visible) - no JS, no portal, no
 * positioning library. Fine for short labels anchored to a fixed spot
 * like icon-only toolbar buttons. */
export function Tooltip({
  label,
  children,
  side = "top",
}: {
  label: string;
  children: ReactNode;
  side?: "top" | "bottom";
}) {
  const positionClass =
    side === "top" ? "bottom-full mb-1.5" : "top-full mt-1.5";
  return (
    <span className="group/tooltip relative inline-flex">
      {children}
      <span
        role="tooltip"
        className={`pointer-events-none absolute left-1/2 ${positionClass} -translate-x-1/2 whitespace-nowrap rounded-[var(--radius-sm)] bg-foreground px-2 py-1 text-[11px] font-medium text-background opacity-0 shadow-[var(--shadow-sm)] transition-opacity delay-300 group-hover/tooltip:opacity-100 group-focus-within/tooltip:opacity-100 group-hover/tooltip:delay-300`}
      >
        {label}
      </span>
    </span>
  );
}
