import { LucideIcon, Spade } from "lucide-react";
import { CardGameKind } from "./types";

export interface CardGameRegistryEntry {
  kind: CardGameKind;
  label: string;
  icon: LucideIcon;
  emoji: string;
}

export const CARD_GAME_REGISTRY: Record<CardGameKind, CardGameRegistryEntry> = {
  poker: {
    kind: "poker",
    label: "Poker",
    icon: Spade,
    // Not a poker chip (no dedicated emoji exists) and deliberately not
    // the newer U+1FA99 coin emoji either - that one's from Unicode 13.0
    // (2020) and still renders as a blank box on some systems' font
    // stacks. 🎰 is long-established (Unicode 6.0) and reads as "casino
    // game" clearly enough, without colliding with Draft's 🃏 above it.
    emoji: "🎰",
  },
};
