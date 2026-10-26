"use client";

import { Menu, Hash, Users, Video } from "lucide-react";
import { useRoomStore } from "@/lib/store";
import { Tooltip } from "@/components/ui/Tooltip";
import { DropdownMenu, DropdownItem } from "@/components/ui/DropdownMenu";

export function ConversationHeader({
  onOpenSidebar,
  onToggleMembers,
  membersOpen,
  onOpenWebRTCCall,
  onOpenJitsiCall,
}: {
  onOpenSidebar: () => void;
  onToggleMembers: () => void;
  membersOpen: boolean;
  onOpenWebRTCCall: () => void;
  onOpenJitsiCall: () => void;
}) {
  const channels = useRoomStore((s) => s.channels);
  const activeChannelId = useRoomStore((s) => s.activeChannelId);
  const onlineCount = useRoomStore((s) => s.online.length);
  const webrtcCallCount = useRoomStore((s) => s.callPresence.webrtc.length);
  const jitsiCallCount = useRoomStore((s) => s.callPresence.jitsi.length);
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
        <DropdownMenu
          align="end"
          trigger={({ toggle, open }) => (
            <Tooltip label="Start a video call">
              <button
                type="button"
                onClick={toggle}
                aria-haspopup="menu"
                aria-expanded={open}
                aria-label="Start a video call"
                className={`flex h-9 w-9 items-center justify-center rounded-[var(--radius-sm)] transition-colors ${
                  open ? "bg-accent-soft text-accent" : "text-muted hover:bg-surface-muted"
                }`}
              >
                <Video size={18} />
              </button>
            </Tooltip>
          )}
        >
          <DropdownItem icon={<Video size={15} />} onClick={onOpenWebRTCCall}>
            WebRTC (P2P){webrtcCallCount > 0 ? ` · ${webrtcCallCount} in call` : ""}
          </DropdownItem>
          <DropdownItem icon={<Video size={15} />} onClick={onOpenJitsiCall}>
            Jitsi Meet{jitsiCallCount > 0 ? ` · ${jitsiCallCount} in call` : ""}
          </DropdownItem>
        </DropdownMenu>

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
