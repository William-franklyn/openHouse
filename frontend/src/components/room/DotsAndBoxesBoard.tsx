import { GameBoardProps } from "@/lib/gameRegistry";

const PAD = 0.3; // margin around the grid, in box-units

export function DotsAndBoxesBoard({ game, interactive, onMove }: GameBoardProps<"dots_and_boxes">) {
  const rows = game.boxes.length;
  const cols = game.boxes[0]?.length ?? 0;

  return (
    <div className="mx-auto w-full max-w-[min(90vw,380px)]">
      <svg
        viewBox={`${-PAD} ${-PAD} ${cols + PAD * 2} ${rows + PAD * 2}`}
        className="w-full"
        style={{ aspectRatio: `${cols + PAD * 2} / ${rows + PAD * 2}` }}
      >
        {/* Claimed boxes */}
        {game.boxes.map((row, r) =>
          row.map((owner, c) =>
            owner === null ? null : (
              <rect
                key={`box-${r}-${c}`}
                x={c + 0.08}
                y={r + 0.08}
                width={0.84}
                height={0.84}
                rx={0.06}
                fill={owner === 0 ? "var(--accent)" : "#fb7185"}
                opacity={0.35}
              />
            )
          )
        )}

        {/* Horizontal edges */}
        {game.hEdges.map((row, r) =>
          row.map((drawn, c) => (
            <g key={`h-${r}-${c}`}>
              <line
                x1={c}
                y1={r}
                x2={c + 1}
                y2={r}
                strokeWidth={0.22}
                stroke="transparent"
                style={{ cursor: interactive && !drawn ? "pointer" : "default" }}
                onClick={() => interactive && !drawn && onMove({ edge_type: "h", row: r, col: c })}
              />
              <line
                x1={c}
                y1={r}
                x2={c + 1}
                y2={r}
                strokeWidth={drawn ? 0.09 : 0.025}
                strokeLinecap="round"
                stroke={drawn ? "var(--accent)" : "rgba(255,255,255,0.18)"}
                pointerEvents="none"
              />
            </g>
          ))
        )}

        {/* Vertical edges */}
        {game.vEdges.map((row, r) =>
          row.map((drawn, c) => (
            <g key={`v-${r}-${c}`}>
              <line
                x1={c}
                y1={r}
                x2={c}
                y2={r + 1}
                strokeWidth={0.22}
                stroke="transparent"
                style={{ cursor: interactive && !drawn ? "pointer" : "default" }}
                onClick={() => interactive && !drawn && onMove({ edge_type: "v", row: r, col: c })}
              />
              <line
                x1={c}
                y1={r}
                x2={c}
                y2={r + 1}
                strokeWidth={drawn ? 0.09 : 0.025}
                strokeLinecap="round"
                stroke={drawn ? "var(--accent)" : "rgba(255,255,255,0.18)"}
                pointerEvents="none"
              />
            </g>
          ))
        )}

        {/* Dots */}
        {Array.from({ length: rows + 1 }, (_, r) =>
          Array.from({ length: cols + 1 }, (_, c) => (
            <circle key={`dot-${r}-${c}`} cx={c} cy={r} r={0.07} fill="currentColor" className="text-white/70" />
          ))
        )}
      </svg>
    </div>
  );
}
