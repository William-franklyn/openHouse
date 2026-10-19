"use client";

import { useState } from "react";
import { useRoomStore } from "@/lib/store";
import { Button } from "@/components/ui/Button";
import { CreateChannelModal } from "./CreateChannelModal";

export function ChannelTabs({ onCreateChannel }: { onCreateChannel: (name: string) => void }) {
  const channels = useRoomStore((s) => s.channels);
  const activeChannelId = useRoomStore((s) => s.activeChannelId);
  const myRole = useRoomStore((s) => s.myRole);
  const [showCreate, setShowCreate] = useState(false);
  const canCreate = (myRole === "owner" || myRole === "mod") && channels.length < 11;

  return (
    <div className="flex items-center gap-1 overflow-x-auto border-b border-border px-2 py-2">
      {channels.map((c) => (
        <button
          key={c.id}
          onClick={() => useRoomStore.getState().setActiveChannel(c.id)}
          className={`shrink-0 rounded-full px-3 py-1.5 text-sm ${
            c.id === activeChannelId ? "bg-accent text-accent-foreground" : "text-muted hover:bg-surface-muted"
          }`}
        >
          #{c.name}
        </button>
      ))}
      {canCreate && (
        <Button variant="ghost" size="sm" onClick={() => setShowCreate(true)}>
          +
        </Button>
      )}
      <CreateChannelModal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreate={(name) => {
          onCreateChannel(name);
          setShowCreate(false);
        }}
      />
    </div>
  );
}
