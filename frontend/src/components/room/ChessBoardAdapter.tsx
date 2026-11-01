import { ChessBoard } from "./ChessBoard";
import { GameBoardProps } from "@/lib/gameRegistry";

/** Wraps the unmodified ChessBoard (zero changes there, including its
 * parabolic move-arrow animation) in the generic registry's Board
 * contract - translating the generic onMove(move) callback into the
 * UCI-slicing {from, to, promotion} shape ChessBoard already expects.
 * This is the exact logic that used to live inline in
 * GameBoardModal.handleMove, relocated here unchanged. */
export function ChessBoardAdapter({ game, orientation, interactive, onMove }: GameBoardProps<"chess">) {
  return (
    <ChessBoard
      boardFen={game.boardFen}
      myColor={orientation}
      turn={game.turn}
      legalMoves={game.legalMoves}
      lastMove={game.lastMove as string | null}
      inCheck={game.inCheck}
      interactive={interactive}
      onMove={(uci) => onMove({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci.slice(4) || undefined })}
    />
  );
}
