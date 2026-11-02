import { Brain, LayoutGrid, LucideIcon, Shuffle } from "lucide-react";
import { PartyGameKind } from "./types";

export interface PartyGameRegistryEntry {
  kind: PartyGameKind;
  label: string;
  icon: LucideIcon;
  emoji: string;
}

export const PARTY_GAME_REGISTRY: Record<PartyGameKind, PartyGameRegistryEntry> = {
  trivia: {
    kind: "trivia",
    label: "Trivia Night",
    icon: Brain,
    emoji: "🧠",
  },
  draft: {
    kind: "draft",
    label: "Card Draft",
    icon: LayoutGrid,
    emoji: "🃏",
  },
  uno: {
    kind: "uno",
    label: "Uno",
    icon: Shuffle,
    emoji: "🔴",
  },
};
