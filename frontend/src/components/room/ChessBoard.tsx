"use client";

import { useMemo, useState } from "react";

// Deliberately the same (filled/"black-style") glyph for both colors -
// the actual "white chess piece" Unicode block (U+2654-2659) renders as a
// hollow outline in most fonts, which doesn't reliably take a CSS color
// override in headless/cross-platform rendering and ends up visually
// indistinguishable from the black pieces. Using one filled glyph set and
// telling the colors apart with a token background (see the square
// rendering below) sidesteps that entirely.
const PIECE_GLYPHS: Record<string, string> = {
  K: "♚", Q: "♛", R: "♜", B: "♝", N: "♞", P: "♟",
  k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟",
};

const PROMOTION_PIECES: { code: string; label: string }[] = [
  { code: "q", label: "♛" },
  { code: "r", label: "♜" },
  { code: "b", label: "♝" },
  { code: "n", label: "♞" },
];

/** Parses just the piece-placement field of a FEN (what the backend sends
 * as board_fen) into grid[rankFrom8][fileFromA] - grid[0] is rank 8,
 * grid[7] is rank 1, matching how FEN itself is written top-to-bottom. */
function parseBoardFen(fen: string): (string | null)[][] {
  return fen.split("/").map((rank) => {
    const row: (string | null)[] = [];
    for (const ch of rank) {
      if (/\d/.test(ch)) {
        for (let i = 0; i < Number(ch); i++) row.push(null);
      } else {
        row.push(ch);
      }
    }
    return row;
  });
}

/** rankIdx/fileIdx are absolute board indices (0,0 = a8), never display
 * (flipped) ones - the render loop already converts back to absolute
 * indices before calling this. */
function squareName(rankIdx: number, fileIdx: number): string {
  const file = String.fromCharCode(97 + fileIdx);
  const rank = 8 - rankIdx;
  return `${file}${rank}`;
}

export function ChessBoard({
  boardFen,
  myColor,
  turn,
  legalMoves,
  lastMove,
  inCheck,
  interactive,
  onMove,
}: {
  boardFen: string;
  myColor: "white" | "black";
  turn: "white" | "black";
  legalMoves: string[];
  lastMove: string | null;
  inCheck: boolean;
  interactive: boolean;
  onMove: (uci: string) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [promotionPick, setPromotionPick] = useState<{ from: string; to: string } | null>(null);

  const grid = useMemo(() => parseBoardFen(boardFen), [boardFen]);
  const flipped = myColor === "black";
  const displayRows = flipped ? [...grid].reverse() : grid;

  const destinationsFromSelected = useMemo(() => {
    if (!selected) return new Set<string>();
    return new Set(
      legalMoves.filter((m) => m.startsWith(selected)).map((m) => m.slice(2, 4))
    );
  }, [selected, legalMoves]);

  const [lastFrom, lastTo] = lastMove ? [lastMove.slice(0, 2), lastMove.slice(2, 4)] : [null, null];
  // in_check describes whoever's turn it currently is (python-chess's
  // board.is_check() checks the side to move) - not tied to myColor, since
  // both players should see the same king highlighted.
  const kingChar = turn === "white" ? "K" : "k";
  const checkedKingSquare = inCheck
    ? (() => {
        for (let r = 0; r < 8; r++) {
          for (let f = 0; f < 8; f++) {
            if (grid[r][f] === kingChar) return squareName(r, f);
          }
        }
        return null;
      })()
    : null;

  function handleSquareClick(sq: string, piece: string | null) {
    if (!interactive || promotionPick) return;

    if (selected && destinationsFromSelected.has(sq)) {
      // A promotion move is a legal e2e4-shaped move with a 5th character
      // (the promotion piece) - the server's legal_moves list is the only
      // source of truth needed here, no pawn/rank heuristic required.
      const isPromotion = legalMoves.some(
        (m) => m.startsWith(selected) && m.slice(2, 4) === sq && m.length === 5
      );

      if (isPromotion) {
        setPromotionPick({ from: selected, to: sq });
      } else {
        onMove(`${selected}${sq}`);
      }
      setSelected(null);
      return;
    }

    const isMine = piece != null && (myColor === "white" ? piece === piece.toUpperCase() : piece === piece.toLowerCase());
    setSelected(isMine ? sq : null);
  }

  function pickPromotion(code: string) {
    if (!promotionPick) return;
    onMove(`${promotionPick.from}${promotionPick.to}${code}`);
    setPromotionPick(null);
  }

  return (
    <div className="relative mx-auto w-full max-w-[min(90vw,440px)]">
      <div className="grid grid-cols-8 overflow-hidden rounded-[var(--radius-md)] border border-border shadow-[var(--shadow-sm)]">
        {displayRows.map((row, rIdxDisplay) => {
          const rIdx = flipped ? 7 - rIdxDisplay : rIdxDisplay;
          const displayRow = flipped ? [...row].reverse() : row;
          return displayRow.map((piece, fIdxDisplay) => {
            const fIdx = flipped ? 7 - fIdxDisplay : fIdxDisplay;
            const sq = squareName(rIdx, fIdx);
            const dark = (rIdx + fIdx) % 2 === 1;
            const isSelected = selected === sq;
            const isDestination = destinationsFromSelected.has(sq);
            const isLastMove = sq === lastFrom || sq === lastTo;
            const isCheckedKing = sq === checkedKingSquare;

            return (
              <button
                key={sq}
                type="button"
                onClick={() => handleSquareClick(sq, piece)}
                disabled={!interactive}
                aria-label={sq}
                className={`relative flex aspect-square items-center justify-center text-[clamp(20px,6vw,34px)] leading-none transition-colors ${
                  dark ? "bg-[#7c93c9]" : "bg-[#eef1f8]"
                } ${isSelected ? "ring-2 ring-inset ring-accent" : ""} ${
                  isCheckedKing ? "bg-danger/60!" : ""
                } ${interactive ? "cursor-pointer" : "cursor-default"}`}
              >
                {isLastMove && <span className="absolute inset-0 bg-accent/20" aria-hidden />}
                {piece && (
                  <span
                    className={`relative flex h-[82%] w-[82%] items-center justify-center rounded-full shadow-sm ${
                      piece === piece.toUpperCase()
                        ? "border border-[#1a1a1a]/25 bg-white text-[#1a1a1a]"
                        : "bg-[#242424] text-white"
                    }`}
                  >
                    {PIECE_GLYPHS[piece]}
                  </span>
                )}
                {isDestination && !piece && (
                  <span className="absolute h-[28%] w-[28%] rounded-full bg-[#1a1a1a]/25" aria-hidden />
                )}
                {isDestination && piece && (
                  <span className="absolute inset-0 rounded-sm ring-[3px] ring-inset ring-[#1a1a1a]/40" aria-hidden />
                )}
              </button>
            );
          });
        })}
      </div>

      {promotionPick && (
        <div className="absolute inset-0 flex items-center justify-center bg-background/90">
          <div className="flex gap-2 rounded-[var(--radius-md)] border border-border bg-surface p-3 shadow-[var(--shadow-lg)]">
            {PROMOTION_PIECES.map((p) => (
              <button
                key={p.code}
                type="button"
                onClick={() => pickPromotion(p.code)}
                className="flex h-12 w-12 items-center justify-center rounded-[var(--radius-sm)] text-3xl text-foreground hover:bg-surface-muted"
                aria-label={`Promote to ${p.code}`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
