"use client";

import { useState } from "react";
import {
  ChessKnight,
  Circle,
  Hash,
  Grid3x3,
  Type,
  Brain,
  Hand,
  Target,
  Dices,
  Spade,
} from "lucide-react";
import { Modal } from "@/components/ui/Modal";

interface GameOption {
  id: string;
  name: string;
  icon: typeof ChessKnight;
  live: boolean;
}

const GAMES: GameOption[] = [
  { id: "chess", name: "Chess", icon: ChessKnight, live: true },
  { id: "checkers", name: "Checkers", icon: Circle, live: false },
  { id: "tictactoe", name: "Tic-Tac-Toe", icon: Hash, live: false },
  { id: "connect4", name: "Connect Four", icon: Grid3x3, live: false },
  { id: "wordguess", name: "Word Guess", icon: Type, live: false },
  { id: "trivia", name: "Trivia Night", icon: Brain, live: false },
  { id: "rps", name: "Rock Paper Scissors", icon: Hand, live: false },
  { id: "darts", name: "Darts", icon: Target, live: false },
  { id: "ludo", name: "Ludo", icon: Dices, live: false },
  { id: "cards", name: "Card Game", icon: Spade, live: false },
];

export function GamesModal({
  open,
  onClose,
  onPickChess,
}: {
  open: boolean;
  onClose: () => void;
  onPickChess: () => void;
}) {
  const [toast, setToast] = useState<string | null>(null);

  function pick(game: GameOption) {
    if (!game.live) {
      setToast(`${game.name} is coming soon!`);
      window.setTimeout(() => setToast(null), 1800);
      return;
    }
    onClose();
    onPickChess();
  }

  return (
    <Modal open={open} onClose={onClose} title="🎮 Games">
      <div className="flex flex-col gap-3">
        <p className="text-[13px] text-muted">
          Play something together while you chat. More games are on the way.
        </p>

        <div className="grid grid-cols-3 gap-2.5">
          {GAMES.map((game) => {
            const Icon = game.icon;
            return (
              <button
                key={game.id}
                type="button"
                onClick={() => pick(game)}
                className={`relative flex flex-col items-center gap-1.5 rounded-[var(--radius-md)] border p-3 text-center transition-colors ${
                  game.live
                    ? "border-accent/40 bg-accent-soft hover:border-accent"
                    : "border-border text-muted hover:bg-surface-muted"
                }`}
              >
                <Icon size={22} className={game.live ? "text-accent" : "text-muted"} />
                <span className={`text-[11px] font-medium leading-tight ${game.live ? "text-foreground" : "text-muted"}`}>
                  {game.name}
                </span>
                {game.live ? (
                  <span className="absolute -top-1.5 -right-1.5 rounded-full bg-accent px-1.5 py-0.5 text-[9px] font-bold text-accent-foreground">
                    PLAY
                  </span>
                ) : (
                  <span className="absolute -top-1.5 -right-1.5 rounded-full border border-border bg-surface px-1.5 py-0.5 text-[9px] font-medium text-muted">
                    SOON
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {toast && (
          <p className="rounded-[var(--radius-sm)] bg-surface-muted px-3 py-2 text-center text-[12px] text-muted">
            {toast}
          </p>
        )}
      </div>
    </Modal>
  );
}
