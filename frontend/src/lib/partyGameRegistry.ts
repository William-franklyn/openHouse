import { Bell, Brain, Heart, LayoutGrid, LucideIcon, Moon, PenTool, Shuffle, Spade, Users } from "lucide-react";
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
  hearts: {
    kind: "hearts",
    label: "Hearts",
    icon: Heart,
    emoji: "♥️",
    minParticipants: 4,
  },
  werewolf: {
    kind: "werewolf",
    label: "Werewolf",
    icon: Moon,
    emoji: "🐺",
    minParticipants: 5,
  },
  spades: {
    kind: "spades",
    label: "Spades",
    icon: Users,
    emoji: "♠️",
    minParticipants: 4,
  },
  buzzer: {
    kind: "buzzer",
    label: "Buzzer Race",
    icon: Bell,
    emoji: "🔔",
    minParticipants: 2,
  },
  drawing: {
    kind: "drawing",
    label: "Drawing & Guess",
    icon: PenTool,
    emoji: "🎨",
    minParticipants: 3,
  },
};
