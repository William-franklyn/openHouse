const PALETTE = [
  "#ef4444", "#f97316", "#f59e0b", "#84cc16",
  "#10b981", "#14b8a6", "#06b6d4", "#3b82f6",
  "#6366f1", "#8b5cf6", "#d946ef", "#ec4899",
];

function colorFor(seed: string): string {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return PALETTE[hash % PALETTE.length];
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

const SIZES = {
  sm: "h-6 w-6 text-[10px]",
  md: "h-9 w-9 text-xs",
  lg: "h-12 w-12 text-sm",
};

export function Avatar({
  name,
  seed,
  size = "md",
}: {
  name: string;
  seed?: string;
  size?: keyof typeof SIZES;
}) {
  return (
    <span
      className={`inline-flex shrink-0 select-none items-center justify-center rounded-full font-semibold text-white ${SIZES[size]}`}
      style={{ backgroundColor: colorFor(seed ?? name) }}
      aria-hidden
    >
      {initials(name)}
    </span>
  );
}
