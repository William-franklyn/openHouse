import { Brain, LayoutGrid, LucideIcon, Shuffle, Spade } from "lucide-react";
import { PartyGameKind } from "./types";

export interface PartyGameRegistryEntry {
  kind: PartyGameKind;
  label: string;
  icon: LucideIcon;
  emoji: string;
  // Mirrors each engine's own MIN_PARTICIPANTS - the lobby's "Begin now"
  // button reads this so a team game like Codenames can't be started
  // below its real floor (2 full teams), not just a flat >= 2 everywhere.
  minParticipants: number;
}

export const PARTY_GAME_REGISTRY: Record<PartyGameKind, PartyGameRegistryEntry> = {
  trivia: {
    kind: "trivia",
    label: "Trivia Night",
    icon: Brain,
    emoji: "🧠",
    minParticipants: 2,
  },
  draft: {
    kind: "draft",
    label: "Card Draft",
    icon: LayoutGrid,
    emoji: "🃏",
    minParticipants: 2,
  },
  uno: {
    kind: "uno",
    label: "Uno",
    icon: Shuffle,
    emoji: "🔴",
    minParticipants: 2,
  },
  codenames: {
    kind: "codenames",
    label: "Codenames",
    icon: Spade,
    emoji: "🕵️",
    minParticipants: 4,
  },
};
