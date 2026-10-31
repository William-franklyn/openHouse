"use client";

import { Menu, Hash, Users, Video, Images, ChessKnight } from "lucide-react";
import { useRoomStore } from "@/lib/store";
import { Tooltip } from "@/components/ui/Tooltip";

export function ConversationHeader({
  onOpenSidebar,
  onToggleMembers,
  membersOpen,
  onOpenStartCall,
  onOpenPhotoWall,
  onOpenGames,
}: {
  onOpenSidebar: () => void;
  onToggleMembers: () => void;
  membersOpen: boolean;
  onOpenStartCall: () => void;
  onOpenPhotoWall: () => void;
  onOpenGames: () => void;
}) {
  const channels = useRoomStore((s) => s.channels);
  const activeChannelId = useRoomStore((s) => s.activeChannelId);
  const onlineCount = useRoomStore((s) => s.online.length);
  const myGameId = useRoomStore((s) => s.myGameId);
  const channel = channels.find((c) => c.id === activeChannelId);

  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-border bg-surface px-3 sm:px-4">
      <div className="flex min-w-0 items-center gap-2">
        <button
          type="button"
          onClick={onOpenSidebar}
          aria-label="Open channel menu"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-sm)] text-muted hover:bg-surface-muted lg:hidden"
        >
          <Menu size={19} />
        </button>
        <Hash size={16} className="shrink-0 text-muted" />
        <h2 className="truncate text-[15px] font-semibold text-foreground">{channel?.name ?? ""}</h2>
        <span className="hidden shrink-0 text-[13px] text-muted sm:inline">
          · {onlineCount} online
        </span>
      </div>

      <div className="flex shrink-0 items-center gap-1">
        <Tooltip label="Start a video call">
          <button
            type="button"
            onClick={onOpenStartCall}
            aria-label="Start a video call"
            className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-sm)] text-muted transition-colors hover:bg-surface-muted"
          >
            <Video size={18} />
          </button>
        </Tooltip>

        <Tooltip label={myGameId ? "Back to your chess game" : "Play chess"}>
          <button
            type="button"
            onClick={onOpenGames}
            aria-label="Games"
            className="relative flex h-9 w-9 items-center justify-center rounded-[var(--radius-sm)] text-muted transition-colors hover:bg-surface-muted"
          >
            <ChessKnight size={18} />
            {myGameId && (
              <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-accent" aria-hidden />
            )}
          </button>
        </Tooltip>

        <Tooltip label="Photo Wall">
          <button
            type="button"
            onClick={onOpenPhotoWall}
            aria-label="Photo Wall"
            className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-sm)] text-muted transition-colors hover:bg-surface-muted"
          >
            <Images size={18} />
          </button>
        </Tooltip>

        <Tooltip label={membersOpen ? "Hide members" : "Show members"}>
          <button
            type="button"
            onClick={onToggleMembers}
            aria-pressed={membersOpen}
            aria-label="Toggle members panel"
            className={`flex h-9 w-9 items-center justify-center rounded-[var(--radius-sm)] transition-colors ${
              membersOpen ? "bg-accent-soft text-accent" : "text-muted hover:bg-surface-muted"
            }`}
          >
            <Users size={18} />
          </button>
        </Tooltip>
      </div>
    </header>
  );
}
