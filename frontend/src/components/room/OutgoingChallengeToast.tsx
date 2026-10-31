"use client";

import { X } from "lucide-react";
import { Spinner } from "@/components/ui/Spinner";
import { useRoomStore } from "@/lib/store";

export function OutgoingChallengeToast({ send }: { send: (type: string, data?: Record<string, unknown>) => void }) {
  const challenge = useRoomStore((s) => s.pendingChallenge);

  if (!challenge) return null;

  function cancel() {
    send("cancel_game", { game_id: challenge!.gameId });
    useRoomStore.getState().setPendingChallenge(null);
  }

  return (
    <div className="animate-slide-up fixed bottom-[max(1rem,env(safe-area-inset-bottom))] left-1/2 z-[60] flex w-[min(92vw,360px)] -translate-x-1/2 items-center gap-3 rounded-[var(--radius-lg)] border border-border bg-surface p-3.5 shadow-[var(--shadow-lg)]">
      <Spinner className="h-4 w-4 shrink-0 text-accent" />
      <p className="min-w-0 flex-1 truncate text-[13px] text-foreground">
        Waiting for <span className="font-semibold">{challenge.opponentName}</span> to accept…
      </p>
      <button
        type="button"
        onClick={cancel}
        aria-label="Cancel challenge"
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-muted hover:bg-surface-muted hover:text-foreground"
      >
        <X size={14} />
      </button>
    </div>
  );
}
