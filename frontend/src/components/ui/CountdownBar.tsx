"use client";

import { useEffect, useState } from "react";

/** A ticking progress bar driven by server-sent absolute timestamps, not
 * a local duration constant - if the backend's round length ever changes,
 * this still renders correctly with zero frontend changes. */
export function CountdownBar({ startedAtMs, deadlineMs }: { startedAtMs: number; deadlineMs: number }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(id);
  }, []);

  const total = Math.max(1, deadlineMs - startedAtMs);
  const pct = Math.max(0, Math.min(1, (deadlineMs - now) / total));

  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-surface-muted">
      <div
        className={`h-full rounded-full transition-[width] ${pct < 0.25 ? "bg-rose-500" : "bg-accent"}`}
        style={{ width: `${pct * 100}%` }}
      />
    </div>
  );
}
