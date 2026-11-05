"use client";

import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { GAME_REGISTRY } from "@/lib/gameRegistry";
import { PARTY_GAME_REGISTRY } from "@/lib/partyGameRegistry";
import { CARD_GAME_REGISTRY } from "@/lib/cardGameRegistry";
import { CardGameKind, GameKind, PartyGameKind } from "@/lib/types";

interface GameOption {
  id: string;
  name: string;
  emoji: string;
  live: boolean;
  minPlayers?: number;
  partyKind?: PartyGameKind;
  cardKind?: CardGameKind;
}

interface Section {
  label: string;
  heading: string;
  games: GameOption[];
}

const BOARD_GAMES: GameOption[] = Object.values(GAME_REGISTRY).map((entry) => ({
  id: entry.kind,
  name: entry.label,
  emoji: entry.emoji,
  live: true,
}));

const PARTY_GAMES: GameOption[] = Object.values(PARTY_GAME_REGISTRY).map((entry) => ({
  id: entry.kind,
  name: entry.label,
  emoji: entry.emoji,
  live: true,
  minPlayers: entry.minParticipants,
  partyKind: entry.kind,
}));

const CARD_GAMES: GameOption[] = Object.values(CARD_GAME_REGISTRY).map((entry) => ({
  id: entry.kind,
  name: entry.label,
  emoji: entry.emoji,
  live: true,
  cardKind: entry.kind,
}));

// Still-unbuilt games stay as "coming soon" placeholders here - once one
// goes live, moving it into GAME_REGISTRY/partyGameRegistry.ts/
// cardGameRegistry.ts is the only change needed for it to show up above
// instead of here.
const COMING_SOON: GameOption[] = [
  { id: "wordguess", name: "Word Guess", emoji: "📝", live: false },
  { id: "rps", name: "Rock Paper Scissors", emoji: "✂️", live: false },
  { id: "darts", name: "Darts", emoji: "🎯", live: false },
  { id: "ludo", name: "Ludo", emoji: "🎲", live: false },
];

const SECTIONS: Section[] = [
  { label: "🎯", heading: "Board Games", games: BOARD_GAMES },
  { label: "🎉", heading: "Party Games", games: PARTY_GAMES },
  { label: "🃏", heading: "Card Games", games: CARD_GAMES },
  { label: "✨", heading: "Coming Soon", games: COMING_SOON },
];

export function GamesModal({
  open,
  onClose,
  onPick,
  onPickParty,
  onPickCard,
}: {
  open: boolean;
  onClose: () => void;
  onPick: (kind: GameKind) => void;
  onPickParty: (kind: PartyGameKind) => void;
  onPickCard: (kind: CardGameKind) => void;
}) {
  const [toast, setToast] = useState<string | null>(null);

  function pick(game: GameOption) {
    if (!game.live) {
      setToast(`${game.name} is coming soon!`);
      window.setTimeout(() => setToast(null), 1800);
      return;
    }
    onClose();
    if (game.partyKind) {
      onPickParty(game.partyKind);
    } else if (game.cardKind) {
      onPickCard(game.cardKind);
    } else {
      onPick(game.id as GameKind);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="🎮 Game Lounge" maxWidthClassName="w-[min(94vw,640px)]">
      <div className="flex flex-col gap-4">
        <p className="text-[13px] text-muted">
          Pick something to play together - everyone in the room can jump in.
        </p>

        <div className="-mr-1.5 flex max-h-[65vh] flex-col gap-5 overflow-y-auto pr-1.5">
          {SECTIONS.map((section) => (
            <div key={section.heading}>
              <h3 className="mb-2.5 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-muted">
                <span className="text-sm leading-none">{section.label}</span>
                {section.heading}
              </h3>
              <div className="grid grid-cols-3 gap-2.5 sm:grid-cols-4">
                {section.games.map((game) => (
                  <button
                    key={game.id}
                    type="button"
                    onClick={() => pick(game)}
                    className={`group relative flex flex-col items-center gap-2 rounded-[var(--radius-lg)] border p-3.5 text-center transition-all duration-150 ${
                      game.live
                        ? "border-border bg-surface-muted hover:-translate-y-0.5 hover:border-accent hover:bg-accent-soft hover:shadow-[var(--shadow-md)]"
                        : "border-border/60 bg-surface-muted/50 opacity-55 hover:opacity-80"
                    }`}
                  >
                    <span
                      className={`flex h-12 w-12 items-center justify-center rounded-full bg-surface text-[26px] leading-none shadow-[var(--shadow-sm)] transition-transform duration-150 ${
                        game.live ? "group-hover:scale-110" : ""
                      }`}
                    >
                      {game.emoji}
                    </span>
                    <span className="text-[12.5px] font-semibold leading-tight text-foreground">
                      {game.name}
                    </span>
                    {game.minPlayers && (
                      <span className="text-[10px] font-medium text-muted">{game.minPlayers}+ players</span>
                    )}
                    {!game.live && (
                      <span className="absolute -top-1.5 -right-1.5 rounded-full border border-border bg-surface px-1.5 py-0.5 text-[9px] font-medium text-muted">
                        SOON
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          ))}
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
