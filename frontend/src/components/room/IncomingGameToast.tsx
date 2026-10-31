"use client";

import { ChessKnight, X } from "lucide-react";
import { useRoomStore } from "@/lib/store";

export function IncomingGameToast({ send }: { send: (type: string, data?: Record<string, unknown>) => void }) {
  const invite = useRoomStore((s) => s.incomingGameInvite);

  if (!invite) return null;

  function accept() {
    send("accept_game", { game_id: invite!.gameId });
    useRoomStore.getState().setIncomingGameInvite(null);
  }

  function decline() {
    send("decline_game", { game_id: invite!.gameId });
    useRoomStore.getState().setIncomingGameInvite(null);
  }

  return (
    <div className="animate-slide-up fixed bottom-[max(1rem,env(safe-area-inset-bottom))] left-1/2 z-[60] w-[min(92vw,360px)] -translate-x-1/2 rounded-[var(--radius-lg)] border border-border bg-surface p-3.5 shadow-[var(--shadow-lg)]">
      <div className="flex items-center gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent">
          <ChessKnight size={16} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-semibold text-foreground">{invite.challengerName}</p>
          <p className="text-[12px] text-muted">wants to play chess</p>
        </div>
      </div>
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          onClick={decline}
          className="flex flex-1 items-center justify-center gap-1.5 rounded-[var(--radius-md)] border border-border py-2 text-[13px] font-medium text-muted hover:bg-surface-muted"
        >
          <X size={14} />
          Decline
        </button>
        <button
          type="button"
          onClick={accept}
          className="flex flex-1 items-center justify-center gap-1.5 rounded-[var(--radius-md)] bg-accent py-2 text-[13px] font-medium text-accent-foreground hover:bg-accent-hover"
        >
          <ChessKnight size={14} />
          Play
        </button>
      </div>
    </div>
  );
}
