import { GameBoardProps } from "@/lib/gameRegistry";

export function TicTacToeBoard({ game, interactive, onMove }: GameBoardProps<"tictactoe">) {
  return (
    <div className="relative mx-auto w-full max-w-[min(90vw,360px)]">
      <div className="grid grid-cols-3 gap-2 rounded-[var(--radius-md)] bg-white/5 p-2">
        {game.board.map((cell, i) => (
          <button
            key={i}
            type="button"
            disabled={!interactive || cell !== null}
            onClick={() => onMove({ cell: i })}
            aria-label={`cell ${i}`}
            className={`flex aspect-square items-center justify-center rounded-[var(--radius-sm)] border border-white/10 bg-white/5 text-[clamp(28px,8vw,44px)] font-black leading-none transition-colors ${
              interactive && cell === null ? "cursor-pointer hover:border-accent/50 hover:bg-white/10" : "cursor-default"
            }`}
          >
            {cell === 0 && <span className="text-accent">X</span>}
            {cell === 1 && <span className="text-rose-400">O</span>}
          </button>
        ))}
      </div>
    </div>
  );
}
