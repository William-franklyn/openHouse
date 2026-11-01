import { ChessKnight, Grid3x3, Hash, LucideIcon } from "lucide-react";
import { GameKind } from "./types";
import { GameState } from "./store";
import { ChessBoardAdapter } from "@/components/room/ChessBoardAdapter";
import { TicTacToeBoard } from "@/components/room/TicTacToeBoard";
import { Connect4Board } from "@/components/room/Connect4Board";

export interface GameBoardProps<K extends GameState["kind"] = GameState["kind"]> {
  game: Extract<GameState, { kind: K }>;
  orientation: "white" | "black";
  interactive: boolean;
  onMove: (move: Record<string, unknown>) => void;
}

export interface GameRegistryEntry {
  kind: GameKind;
  label: string;
  icon: LucideIcon;
  arenaTitle: string;
  emoji: string;
  inviteVerb: string;
  // Each concrete Board component is actually narrower than this (e.g.
  // ChessBoardAdapter only ever receives a ChessGameState) - the registry
  // itself is necessarily type-erased since it stores every kind's board
  // under one key, the same way any plugin/registry pattern loses the
  // specific type at the point of lookup. Each Board's own file keeps
  // full type safety for its one kind.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  Board: (props: GameBoardProps<any>) => ReturnType<React.FC>;
}

export const GAME_REGISTRY: Record<GameKind, GameRegistryEntry> = {
  chess: {
    kind: "chess",
    label: "Chess",
    icon: ChessKnight,
    arenaTitle: "CHESS ARENA",
    emoji: "♟️",
    inviteVerb: "play chess",
    Board: ChessBoardAdapter,
  },
  tictactoe: {
    kind: "tictactoe",
    label: "Tic-Tac-Toe",
    icon: Hash,
    arenaTitle: "TIC-TAC-TOE ARENA",
    emoji: "⭕",
    inviteVerb: "play tic-tac-toe",
    Board: TicTacToeBoard,
  },
  connect4: {
    kind: "connect4",
    label: "Connect Four",
    icon: Grid3x3,
    arenaTitle: "CONNECT FOUR ARENA",
    emoji: "🔴",
    inviteVerb: "play Connect Four",
    Board: Connect4Board,
  },
};
