"use client";

import { Pin } from "lucide-react";
import { useRoomStore } from "@/lib/store";

export function PinnedBanner() {
  const pinnedIds = useRoomStore((s) => s.pinnedIds);
  const messagesByChannel = useRoomStore((s) => s.messagesByChannel);

  if (pinnedIds.length === 0) return null;

  const pinned = pinnedIds.map((id) => {
    for (const messages of Object.values(messagesByChannel)) {
      const found = messages.find((m) => m.id === id);
      if (found) return found;
    }
    return null;
  });

  return (
    <div className="flex flex-col gap-1 border-b border-border bg-accent-soft/50 px-4 py-2">
      {pinned.map((msg, i) => (
        <p key={pinnedIds[i]} className="flex items-center gap-1.5 truncate text-[12px] text-foreground">
          <Pin size={12} className="shrink-0 text-accent" />
          {msg ? (
            <>
              <span className="font-medium">{msg.from_name ?? "Someone"}</span>
              <span className="truncate text-muted">{msg.text}</span>
            </>
          ) : (
            <span className="text-muted">Pinned message</span>
          )}
        </p>
      ))}
    </div>
  );
}
