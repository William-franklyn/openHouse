"use client";

import { useEffect, useState } from "react";
import { Trophy, X } from "lucide-react";
import { Spinner } from "@/components/ui/Spinner";
import { Avatar } from "@/components/ui/Avatar";
import { api } from "@/lib/api";
import { LeaderboardRow } from "@/lib/types";

const MEDALS = ["🥇", "🥈", "🥉"];

export function LeaderboardPanel({
  open,
  onClose,
  roomId,
  token,
}: {
  open: boolean;
  onClose: () => void;
  roomId: string;
  token: string;
}) {
  const [rows, setRows] = useState<LeaderboardRow[] | null>(null);

  useEffect(() => {
    if (!open) return;
    setRows(null);
    api
      .gamesLeaderboard(roomId, token)
      .then((res) => setRows(res.rows))
      .catch(() => setRows([]));
  }, [open, roomId, token]);

  if (!open) return null;

  return (
    <div className="absolute inset-0 z-20 flex flex-col bg-[#120d24]/97 text-white">
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-white/10 px-4">
        <div className="flex items-center gap-2">
          <Trophy size={16} className="text-amber-400" />
          <h3 className="text-[13px] font-bold tracking-wide">LEADERBOARD</h3>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close leaderboard"
          className="flex h-7 w-7 items-center justify-center rounded-full text-white/60 hover:bg-white/10 hover:text-white"
        >
          <X size={15} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {rows === null ? (
          <div className="flex justify-center py-10">
            <Spinner className="h-5 w-5 text-violet-400" />
          </div>
        ) : rows.length === 0 ? (
          <p className="px-2 py-10 text-center text-[13px] text-white/50">
            No games finished in this room yet. Be the first!
          </p>
        ) : (
          <div className="flex flex-col gap-1.5">
            {rows.map((row, i) => (
              <div
                key={row.member_id}
                className={`flex items-center gap-3 rounded-[var(--radius-md)] border px-3 py-2.5 ${
                  i === 0
                    ? "border-amber-400/40 bg-amber-400/10"
                    : "border-white/10 bg-white/5"
                }`}
              >
                <span className="w-6 shrink-0 text-center text-[15px]">
                  {MEDALS[i] ?? `#${i + 1}`}
                </span>
                <Avatar name={row.name} seed={row.member_id} size="sm" />
                <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">{row.name}</span>
                <div className="flex shrink-0 items-center gap-2.5 text-[11px] font-medium">
                  <span className="text-emerald-400">{row.wins}W</span>
                  <span className="text-rose-400">{row.losses}L</span>
                  <span className="text-white/50">{row.draws}D</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
