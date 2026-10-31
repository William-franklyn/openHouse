"use client";

import { useEffect, useMemo, useRef, useState } from "react";

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

/** Center of a square in display (post-flip) grid units, for drawing the
 * move arrow - same flip transform the render loop applies to pieces,
 * just run directly off the square name instead of a loop index. */
function squareCenter(sq: string, flipped: boolean): [number, number] {
  const fIdx = sq.charCodeAt(0) - 97;
  const rIdx = 8 - Number(sq[1]);
  const col = flipped ? 7 - fIdx : fIdx;
  const row = flipped ? 7 - rIdx : rIdx;
  return [col + 0.5, row + 0.5];
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

      {lastFrom && lastTo && <MoveArrow key={lastMove} from={lastFrom} to={lastTo} flipped={flipped} />}

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

const MOVE_JUMP_DURATION_MS = 1100;
// A "back" ease - overshoots slightly past its target before settling,
// which is what sells the jump/hop feel rather than a flat glide.
const MOVE_JUMP_EASING = "cubic-bezier(0.34, 1.56, 0.64, 1)";

/** A piece "hopping" from one square to another along a small parabolic
 * arc, so a just-played move reads instantly to anyone watching - players
 * mid-game and especially spectators, who otherwise have to work out what
 * happened from a static before/after board. Driven by the Web Animations
 * API rather than a CSS class, so it's guaranteed to actually play every
 * time a fresh instance mounts (keyed by the caller on the move itself)
 * instead of depending on paint timing to pick up a class change. */
function MoveArrow({ from, to, flipped }: { from: string; to: string; flipped: boolean }) {
  const pathRef = useRef<SVGPathElement>(null);
  const dotRef = useRef<SVGCircleElement>(null);
  const glowRef = useRef<SVGCircleElement>(null);
  const ringRef = useRef<SVGCircleElement>(null);

  const [x1, y1] = squareCenter(from, flipped);
  const [x2, y2] = squareCenter(to, flipped);

  // Control point for a quadratic bezier arc, bulged perpendicular to
  // the move's own direction - NOT a fixed screen-up offset, which would
  // collapse to a flat line for any perfectly vertical move (e2-e4 being
  // the single most common move in chess). Taller for a longer move,
  // capped so a cross-board queen slide doesn't launch off the board.
  const dx = x2 - x1;
  const dy = y2 - y1;
  const dist = Math.hypot(dx, dy) || 1;
  let px = -dy / dist;
  let py = dx / dist;
  if (py > 0) {
    px = -px;
    py = -py;
  }
  const bulge = Math.min(1.5, Math.max(0.4, dist * 0.32));
  const cx = (x1 + x2) / 2 + px * bulge;
  const cy = (y1 + y2) / 2 + py * bulge;
  const d = `M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`;

  useEffect(() => {
    const path = pathRef.current;
    const dot = dotRef.current;
    const glow = glowRef.current;
    const ring = ringRef.current;
    if (!path || !dot || !glow || !ring) return;

    const length = path.getTotalLength();
    path.style.setProperty("stroke-dasharray", `${length}`);

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      // Settle immediately at the fully-drawn, fully-landed state - no
      // travel, no pulse, just a brief static trail.
      path.style.setProperty("stroke-dashoffset", "0");
      [dot, glow].forEach((el) => el.style.setProperty("offset-distance", "100%"));
      return;
    }

    const travel = [
      { offsetDistance: "0%", opacity: 0, offset: 0, easing: MOVE_JUMP_EASING },
      { offsetDistance: "10%", opacity: 1, offset: 0.08 },
      { offsetDistance: "100%", opacity: 1, offset: 0.55 },
      { offsetDistance: "100%", opacity: 1, offset: 0.78 },
      { offsetDistance: "100%", opacity: 0, offset: 1 },
    ];
    dot.animate(travel, { duration: MOVE_JUMP_DURATION_MS, fill: "forwards" });
    glow.animate(travel, { duration: MOVE_JUMP_DURATION_MS, fill: "forwards" });

    path.animate(
      [
        { strokeDashoffset: length, opacity: 1, offset: 0, easing: MOVE_JUMP_EASING },
        { strokeDashoffset: 0, opacity: 1, offset: 0.55 },
        { strokeDashoffset: 0, opacity: 1, offset: 0.78 },
        { strokeDashoffset: 0, opacity: 0, offset: 1 },
      ],
      { duration: MOVE_JUMP_DURATION_MS, fill: "forwards" }
    );

    // A small ripple at the landing square the instant the piece arrives.
    ring.animate(
      [
        { transform: "scale(0)", opacity: 0, offset: 0 },
        { transform: "scale(0)", opacity: 0, offset: 0.52 },
        { transform: "scale(1)", opacity: 0.6, offset: 0.6, easing: "ease-out" },
        { transform: "scale(1.8)", opacity: 0, offset: 0.92 },
        { transform: "scale(1.8)", opacity: 0, offset: 1 },
      ],
      { duration: MOVE_JUMP_DURATION_MS, fill: "forwards" }
    );
  }, [from, to, flipped]);

  return (
    <svg
      className="pointer-events-none absolute inset-0 h-full w-full"
      viewBox="0 0 8 8"
      style={{ overflow: "visible", filter: "drop-shadow(0 2px 3px rgba(0,0,0,0.35))" }}
      aria-hidden
    >
      <defs>
        <filter id="chess-arrow-glow-blur" x="-100%" y="-100%" width="300%" height="300%">
          <feGaussianBlur stdDeviation="0.12" />
        </filter>
      </defs>

      <path ref={pathRef} d={d} fill="none" strokeWidth="0.09" strokeLinecap="round" style={{ stroke: "var(--accent)" }} />

      <circle
        ref={ringRef}
        cx={x2}
        cy={y2}
        r="0.32"
        fill="none"
        strokeWidth="0.06"
        style={{ stroke: "var(--accent)", transformBox: "fill-box", transformOrigin: "center" }}
      />

      <circle
        ref={glowRef}
        r="0.26"
        style={{ fill: "var(--accent)", opacity: 0.4, offsetPath: `path('${d}')` }}
        filter="url(#chess-arrow-glow-blur)"
      />
      <circle ref={dotRef} r="0.11" style={{ fill: "var(--accent)", offsetPath: `path('${d}')` }} />
    </svg>
  );
}
