import { useState } from "react";
import { GameBoardProps } from "@/lib/gameRegistry";

const BAR = -1;
const OFF = 24;
const MAX_SHOWN = 5;

function Checker({ seat, count }: { seat: 0 | 1; count: number }) {
  return (
    <div
      className={`flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold shadow-sm ${
        seat === 0 ? "border border-[#1a1a1a]/25 bg-white text-[#1a1a1a]" : "bg-[#242424] text-white"
      }`}
    >
      {count > 1 ? count : ""}
    </div>
  );
}

function Stack({ seat, count }: { seat: 0 | 1; count: number }) {
  if (count === 0) return null;
  const shown = Math.min(count, MAX_SHOWN);
  return (
    <div className="flex flex-col items-center gap-0.5">
      {Array.from({ length: shown }, (_, i) => (
        <Checker key={i} seat={seat} count={i === shown - 1 ? count - shown + 1 : 1} />
      ))}
    </div>
  );
}

export function BackgammonBoard({ game, orientation, interactive, onMove }: GameBoardProps<"backgammon">) {
  const [selected, setSelected] = useState<number | null>(null);
  const mySeat = orientation === "white" ? 0 : 1;

  const destinations = new Set(
    selected === null ? [] : game.legalMoves.filter((m) => m.from === selected).map((m) => m.to)
  );
  const selectableFrom = new Set(game.legalMoves.map((m) => m.from));

  function select(point: number) {
    if (!interactive) return;
    if (selected !== null && destinations.has(point)) {
      onMove({ from: selected, to: point });
      setSelected(null);
      return;
    }
    if (selectableFrom.has(point)) {
      setSelected(point);
    } else {
      setSelected(null);
    }
  }

  // Display order: always points 23..0 left-to-right on top, 0..23 left
  // to right implied on bottom via the mirrored column layout below -
  // flipped for black so each player's own checkers visually travel the
  // same direction regardless of seat.
  const topPoints = orientation === "white" ? [23, 22, 21, 20, 19, 18, 17, 16, 15, 14, 13, 12] : [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11];
  const bottomPoints = orientation === "white" ? [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11] : [23, 22, 21, 20, 19, 18, 17, 16, 15, 14, 13, 12];

  function renderPoint(point: number, topHalf: boolean) {
    const count = game.points[point];
    const seat: 0 | 1 = count >= 0 ? 0 : 1;
    const isSelected = selected === point;
    const isDestination = destinations.has(point);
    const midGap = point === 5 || point === 6 || point === 17 || point === 18;
    return (
      <button
        key={point}
        type="button"
        onClick={() => select(point)}
        aria-label={`point ${point + 1}`}
        className={`relative flex min-h-[90px] flex-1 flex-col items-center justify-start gap-1 border border-white/5 px-0.5 py-1.5 ${
          topHalf ? "justify-start" : "flex-col-reverse justify-start"
        } ${(topHalf ? Math.floor(topPoints.indexOf(point) / 6) : Math.floor(bottomPoints.indexOf(point) / 6)) % 2 === 0 ? "bg-amber-900/25" : "bg-black/10"} ${
          isDestination ? "ring-2 ring-inset ring-accent cursor-pointer" : ""
        } ${isSelected ? "bg-accent/20" : ""} ${midGap ? "mr-2" : ""}`}
      >
        {isDestination && <span className="absolute inset-0 m-auto h-2.5 w-2.5 rounded-full bg-accent/60" aria-hidden />}
        {Math.abs(count) > 0 && <Stack seat={seat} count={Math.abs(count)} />}
      </button>
    );
  }

  return (
    <div className="mx-auto w-full max-w-[min(94vw,520px)]">
      <div className="flex items-center justify-center gap-3 pb-2 text-[12px] text-white/60">
        <span>Dice: {game.dice.join(" , ")}</span>
        <span>· Remaining: {game.remainingDice.join(", ") || "none"}</span>
      </div>

      <div className="flex gap-1 rounded-[var(--radius-md)] bg-[#2b1a0f] p-1.5">
        {topPoints.map((p) => renderPoint(p, true))}
      </div>
      <div className="flex gap-1 rounded-[var(--radius-md)] bg-[#2b1a0f] p-1.5">
        {bottomPoints.map((p) => renderPoint(p, false))}
      </div>

      <div className="mt-2 flex items-center justify-center gap-4 text-[11px] text-white/70">
        <button
          type="button"
          onClick={() => select(BAR)}
          disabled={!interactive || !selectableFrom.has(BAR)}
          className={`flex items-center gap-1.5 rounded-[var(--radius-sm)] border border-white/10 px-2.5 py-1.5 ${
            selectableFrom.has(BAR) ? "hover:border-accent/50" : "opacity-50"
          } ${selected === BAR ? "bg-accent/20" : ""}`}
        >
          Bar: W {game.bar[0]} · B {game.bar[1]}
        </button>
        <button
          type="button"
          onClick={() => select(OFF)}
          disabled={!interactive || !destinations.has(OFF)}
          className={`rounded-[var(--radius-sm)] border border-white/10 px-2.5 py-1.5 ${
            destinations.has(OFF) ? "ring-2 ring-accent" : "opacity-50"
          }`}
        >
          Bear off: W {game.borneOff[0]} · B {game.borneOff[1]}
        </button>
      </div>
      <p className="mt-1 text-center text-[11px] text-white/40">You are {mySeat === 0 ? "White" : "Black"}</p>
    </div>
  );
}
