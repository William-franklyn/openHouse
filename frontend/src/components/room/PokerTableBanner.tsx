"use client";

import { useRoomStore } from "@/lib/store";
import { CARD_GAME_REGISTRY } from "@/lib/cardGameRegistry";

/** A slim discovery strip for an open poker table, same spirit as
 * PartyGameBanner - only shown while status is "lobby" and I haven't
 * taken a seat yet. */
export function PokerTableBanner({
  myMemberId,
  send,
}: {
  myMemberId: string;
  send: (type: string, data?: Record<string, unknown>) => void;
}) {
  const game = useRoomStore((s) => s.myCardGame);

  if (!game || game.status !== "lobby" || game.participantIds.includes(myMemberId)) return null;

  const { emoji, label } = CARD_GAME_REGISTRY[game.kind];

  function join() {
    send("join_card_game", { card_game_id: game!.cardGameId });
  }

  return (
    <div className="flex shrink-0 items-center gap-2 overflow-x-auto border-b border-border bg-accent-soft/40 px-3 py-1.5">
      <button
        type="button"
        onClick={join}
        className="flex shrink-0 items-center gap-1.5 rounded-full border border-accent/30 bg-surface px-2.5 py-1 text-[11px] font-medium text-foreground transition-colors hover:border-accent hover:bg-accent-soft"
      >
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-rose-400 opacity-75" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-rose-500" />
        </span>
        {emoji} {label} · {game.participantIds.length} seated
        <span className="text-accent">Join</span>
      </button>
    </div>
  );
}
