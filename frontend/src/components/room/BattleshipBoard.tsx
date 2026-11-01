import { GameBoardProps } from "@/lib/gameRegistry";
import { BattleshipCell } from "@/lib/types";

function Grid({
  cells,
  interactive,
  onFire,
  testId,
}: {
  cells: BattleshipCell[][];
  interactive: boolean;
  onFire?: (row: number, col: number) => void;
  testId: string;
}) {
  return (
    <div data-testid={testId} className="grid grid-cols-10 gap-[2px] rounded-[var(--radius-md)] bg-sky-950/60 p-1.5">
      {cells.map((row, r) =>
        row.map((cell, c) => {
          const clickable = interactive && cell === "unknown";
          return (
            <button
              key={`${r}-${c}`}
              type="button"
              disabled={!clickable}
              onClick={() => onFire?.(r, c)}
              aria-label={`${testId} cell ${r} ${c}`}
              data-cell={cell}
              className={`relative flex aspect-square items-center justify-center rounded-[2px] text-[clamp(8px,2.4vw,13px)] transition-colors ${
                cell === "ship"
                  ? "bg-slate-400/80"
                  : cell === "hit"
                    ? "bg-rose-600"
                    : cell === "miss"
                      ? "bg-sky-800/80"
                      : "bg-sky-900/50"
              } ${clickable ? "cursor-pointer hover:bg-sky-700/70" : "cursor-default"}`}
            >
              {cell === "hit" && "🔥"}
              {cell === "miss" && <span className="h-[26%] w-[26%] rounded-full bg-white/40" aria-hidden />}
            </button>
          );
        })
      )}
    </div>
  );
}

function FleetStatus({ label, hits, sizes }: { label: string; hits: number[]; sizes: number[] }) {
  const sunk = hits.filter((h, i) => h === sizes[i]).length;
  return (
    <p className="text-center text-[11px] font-semibold text-white/50">
      {label}: {sunk}/{sizes.length} ships sunk
    </p>
  );
}

export function BattleshipBoard({ game, orientation, interactive, onMove }: GameBoardProps<"battleship">) {
  const mySeat = orientation === "white" ? 0 : 1;
  const opponentSeat = 1 - mySeat;
  const myGrid = orientation === "white" ? game.whiteGrid : game.blackGrid;
  const targetGrid = orientation === "white" ? game.blackGrid : game.whiteGrid;

  return (
    <div className="mx-auto flex w-full max-w-[min(90vw,420px)] flex-col gap-4">
      <div>
        <p className="mb-1.5 text-center text-[11px] font-bold uppercase tracking-wide text-rose-300/80">
          Target grid - tap to fire
        </p>
        <Grid
          testId="target-grid"
          cells={targetGrid}
          interactive={interactive}
          onFire={(row, col) => onMove({ row, col })}
        />
        <FleetStatus label="Enemy fleet" hits={game.shipHits[opponentSeat]} sizes={game.shipSizes} />
      </div>
      <div>
        <p className="mb-1.5 text-center text-[11px] font-bold uppercase tracking-wide text-sky-300/80">Your fleet</p>
        <Grid testId="my-grid" cells={myGrid} interactive={false} />
        <FleetStatus label="Your fleet" hits={game.shipHits[mySeat]} sizes={game.shipSizes} />
      </div>
    </div>
  );
}
