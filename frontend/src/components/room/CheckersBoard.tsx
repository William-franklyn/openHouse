import { useEffect, useState } from "react";
import { GameBoardProps } from "@/lib/gameRegistry";

const PIECE_GLYPH: Record<string, string> = { w: "●", wk: "♚", b: "●", bk: "♚" };

export function CheckersBoard({ game, orientation, interactive, onMove }: GameBoardProps<"checkers">) {
  const [selected, setSelected] = useState<[number, number] | null>(null);
  const flipped = orientation === "black";

  // A forced multi-jump continuation always has exactly one answer for
  // "which piece" - keep it selected automatically so the player can
  // just tap destinations without re-picking the same piece each hop.
  useEffect(() => {
    setSelected(game.mustContinueFrom ?? null);
  }, [game.mustContinueFrom]);

  const destinations = selected
    ? game.legalMoves.filter((m) => m.from[0] === selected[0] && m.from[1] === selected[1]).map((m) => m.to)
    : [];
  const selectableFrom = new Set(game.legalMoves.map((m) => `${m.from[0]},${m.from[1]}`));

  function handleClick(r: number, c: number) {
    if (!interactive) return;
    const isDestination = destinations.some(([dr, dc]) => dr === r && dc === c);
    if (selected && isDestination) {
      onMove({ from: selected, to: [r, c] });
      setSelected(null);
      return;
    }
    if (game.mustContinueFrom) return; // locked to the continuing piece
    const piece = game.board[r][c];
    const mine = piece != null && (orientation === "white" ? piece.startsWith("w") : piece.startsWith("b"));
    if (mine && selectableFrom.has(`${r},${c}`)) {
      setSelected([r, c]);
    } else {
      setSelected(null);
    }
  }

  const displayRows = flipped ? [...game.board].reverse() : game.board;

  return (
    <div className="mx-auto w-full max-w-[min(90vw,420px)]">
      <div className="grid grid-cols-8 overflow-hidden rounded-[var(--radius-md)] border border-white/10">
        {displayRows.map((row, rDisp) => {
          const r = flipped ? 7 - rDisp : rDisp;
          const displayRow = flipped ? [...row].reverse() : row;
          return displayRow.map((piece, cDisp) => {
            const c = flipped ? 7 - cDisp : cDisp;
            const dark = (r + c) % 2 === 1;
            const isSelected = selected?.[0] === r && selected?.[1] === c;
            const isDestination = destinations.some(([dr, dc]) => dr === r && dc === c);
            return (
              <button
                key={`${r}-${c}`}
                type="button"
                disabled={!dark || !interactive}
                onClick={() => handleClick(r, c)}
                aria-label={`square ${r} ${c}`}
                className={`relative flex aspect-square items-center justify-center text-[clamp(18px,5vw,28px)] ${
                  dark ? "bg-[#7c93c9]" : "bg-[#eef1f8]"
                } ${isSelected ? "ring-2 ring-inset ring-accent" : ""}`}
              >
                {isDestination && <span className="absolute h-[26%] w-[26%] rounded-full bg-accent/50" aria-hidden />}
                {piece && (
                  <span
                    className={`flex h-[78%] w-[78%] items-center justify-center rounded-full shadow-sm ${
                      piece.startsWith("w") ? "border border-[#1a1a1a]/25 bg-white text-[#1a1a1a]" : "bg-[#242424] text-white"
                    }`}
                  >
                    {PIECE_GLYPH[piece]}
                  </span>
                )}
              </button>
            );
          });
        })}
      </div>
    </div>
  );
}
