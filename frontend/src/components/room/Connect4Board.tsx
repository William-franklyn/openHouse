import { GameBoardProps } from "@/lib/gameRegistry";

const COLS = 7;

export function Connect4Board({ game, interactive, onMove }: GameBoardProps<"connect4">) {
  const openColumns = new Set(game.legalMoves.map((m) => m.column));

  return (
    <div className="mx-auto flex w-full max-w-[min(90vw,420px)] flex-col gap-1.5">
      <div className="flex gap-1.5">
        {Array.from({ length: COLS }, (_, c) => {
          const open = interactive && openColumns.has(c);
          return (
            <button
              key={c}
              type="button"
              disabled={!open}
              onClick={() => onMove({ column: c })}
              aria-label={`drop in column ${c + 1}`}
              className={`flex-1 rounded-t-[var(--radius-sm)] border border-white/10 py-1.5 text-white/50 transition-colors ${
                open ? "cursor-pointer hover:border-accent/50 hover:bg-white/10 hover:text-accent" : "cursor-default opacity-30"
              }`}
            >
              ↓
            </button>
          );
        })}
      </div>
      <div className="flex flex-col gap-1.5 rounded-[var(--radius-md)] bg-blue-950/50 p-1.5">
        {game.board.map((row, r) => (
          <div key={r} className="flex gap-1.5">
            {row.map((cell, c) => (
              <div
                key={c}
                className={`aspect-square flex-1 rounded-full border border-white/5 shadow-inner ${
                  cell === 0 ? "bg-rose-500" : cell === 1 ? "bg-amber-400" : "bg-white/10"
                }`}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
