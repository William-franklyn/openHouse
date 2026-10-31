"use client";

import { Flag, X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { useRoomStore } from "@/lib/store";
import { ChessBoard } from "./ChessBoard";

export function GameBoardModal({
  open,
  onClose,
  myMemberId,
  send,
}: {
  open: boolean;
  onClose: () => void;
  myMemberId: string;
  send: (type: string, data?: Record<string, unknown>) => void;
}) {
  const game = useRoomStore((s) => s.game);

  if (!open || !game) return null;

  const myColor: "white" | "black" = game.whiteMemberId === myMemberId ? "white" : "black";
  const opponentName = myColor === "white" ? game.blackName : game.whiteName;
  const isMyTurn = game.turn === myColor;

  function handleMove(uci: string) {
    const [from, to, promotion] = [uci.slice(0, 2), uci.slice(2, 4), uci.slice(4) || undefined];
    send("game_move", { game_id: game!.gameId, from, to, promotion });
  }

  function handleResign() {
    send("resign_game", { game_id: game!.gameId });
  }

  let banner: string | null = null;
  if (game.gameOver) {
    if (game.result === "draw") {
      banner = `Draw — ${(game.termination ?? "").replace(/_/g, " ")}`;
    } else {
      const iWon = game.result === myColor;
      banner = iWon ? "You won! ♟️" : "You lost — better luck next time.";
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="flex max-h-[90vh] w-full max-w-lg flex-col overflow-hidden rounded-[var(--radius-lg)] border border-border bg-surface shadow-[var(--shadow-lg)]">
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-border px-4">
          <div>
            <h2 className="text-[15px] font-semibold text-foreground">Chess vs {opponentName}</h2>
            <p className="text-[11px] text-muted">
              You're playing {myColor}
              {game.status === "active" && ` · ${isMyTurn ? "Your move" : `Waiting for ${opponentName}`}`}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="flex h-8 w-8 items-center justify-center rounded-full text-muted hover:bg-surface-muted hover:text-foreground"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {banner && (
            <p className="mb-3 rounded-[var(--radius-md)] bg-accent-soft px-3 py-2 text-center text-[13px] font-medium text-accent">
              {banner}
            </p>
          )}
          {!game.gameOver && game.inCheck && (
            <p className="mb-3 text-center text-[13px] font-medium text-danger">Check!</p>
          )}
          <ChessBoard
            boardFen={game.boardFen}
            myColor={myColor}
            turn={game.turn}
            legalMoves={game.legalMoves}
            lastMove={game.lastMove}
            inCheck={game.inCheck}
            interactive={game.status === "active" && isMyTurn}
            onMove={handleMove}
          />
        </div>

        {game.status === "active" && (
          <div className="flex h-14 shrink-0 items-center justify-center border-t border-border">
            <Button variant="danger" size="sm" onClick={handleResign}>
              <Flag size={14} />
              Resign
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
