"use client";

import { Eye } from "lucide-react";
import { useRoomStore } from "@/lib/store";

/** A slim, non-interrupting strip for games other people in the room are
 * currently playing - deliberately not a toast or modal, since the whole
 * point is other people can keep chatting/doing their own thing and only
 * glance at this if they want to. */
export function LiveGamesBanner({ send }: { send: (type: string, data?: Record<string, unknown>) => void }) {
  const liveGames = useRoomStore((s) => s.liveGames);
  const watcherCounts = useRoomStore((s) => s.watcherCounts);
  const games = Object.values(liveGames);

  if (games.length === 0) return null;

  function watch(gameId: string) {
    send("watch_game", { game_id: gameId });
    useRoomStore.getState().setWatchingGameId(gameId);
  }

  return (
    <div className="flex shrink-0 items-center gap-2 overflow-x-auto border-b border-border bg-accent-soft/40 px-3 py-1.5">
      {games.map((g) => {
        const count = watcherCounts[g.gameId] ?? 0;
        return (
          <button
            key={g.gameId}
            type="button"
            onClick={() => watch(g.gameId)}
            className="flex shrink-0 items-center gap-1.5 rounded-full border border-accent/30 bg-surface px-2.5 py-1 text-[11px] font-medium text-foreground transition-colors hover:border-accent hover:bg-accent-soft"
          >
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-rose-400 opacity-75" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-rose-500" />
            </span>
            ♟️ {g.whiteName} vs {g.blackName}
            {count > 0 && (
              <span className="flex items-center gap-0.5 text-muted">
                <Eye size={10} /> {count}
              </span>
            )}
            <span className="text-accent">Watch</span>
          </button>
        );
      })}
    </div>
  );
}
