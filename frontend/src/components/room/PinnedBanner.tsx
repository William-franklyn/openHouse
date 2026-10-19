"use client";

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
    <div className="flex flex-col gap-1 border-b border-border bg-surface-muted px-4 py-2">
      {pinned.map((msg, i) => (
        <p key={pinnedIds[i]} className="truncate text-xs">
          📌 {msg ? `${msg.from_name ?? "Someone"}: ${msg.text}` : "Pinned message"}
        </p>
      ))}
    </div>
  );
}
