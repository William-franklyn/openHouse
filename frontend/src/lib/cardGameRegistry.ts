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
    emoji: "\u{1fa99}",
  },
};
