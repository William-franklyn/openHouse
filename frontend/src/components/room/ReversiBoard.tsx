import { GameBoardProps } from "@/lib/gameRegistry";

export function ReversiBoard({ game, interactive, onMove }: GameBoardProps<"reversi">) {
  const legal = new Set(game.legalMoves.map((m) => `${m.row}-${m.col}`));

  return (
    <div className="mx-auto w-full max-w-[min(90vw,420px)]">
      <div className="grid grid-cols-8 gap-0.5 rounded-[var(--radius-md)] bg-emerald-900/50 p-1.5">
        {game.board.map((row, r) =>
          row.map((cell, c) => {
            const isLegal = interactive && legal.has(`${r}-${c}`);
            return (
              <button
                key={`${r}-${c}`}
                type="button"
                disabled={!isLegal}
                onClick={() => onMove({ row: r, col: c })}
                aria-label={`cell ${r} ${c}`}
                className={`relative flex aspect-square items-center justify-center rounded-[2px] bg-emerald-800/60 transition-colors ${
                  isLegal ? "cursor-pointer hover:bg-emerald-700/60" : "cursor-default"
                }`}
              >
                {cell !== null && (
                  <span
                    className={`h-[78%] w-[78%] rounded-full shadow-sm ${
                      cell === 0 ? "bg-white" : "bg-[#1a1a1a]"
                    }`}
                  />
                )}
                {cell === null && isLegal && <span className="h-[22%] w-[22%] rounded-full bg-white/25" aria-hidden />}
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}
