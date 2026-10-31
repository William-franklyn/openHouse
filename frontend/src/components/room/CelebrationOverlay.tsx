"use client";

import { useEffect, useMemo, useState } from "react";

const CONFETTI_COLORS = ["#f59e0b", "#ec4899", "#8b5cf6", "#22d3ee", "#34d399", "#f43f5e"];

interface ConfettiPiece {
  id: number;
  x: string;
  rotate: string;
  delay: string;
  duration: string;
  color: string;
  left: string;
}

function makeConfetti(count: number): ConfettiPiece[] {
  return Array.from({ length: count }, (_, i) => ({
    id: i,
    x: `${Math.round((Math.random() - 0.5) * 60)}px`,
    rotate: `${Math.round(360 + Math.random() * 360)}deg`,
    delay: `${(Math.random() * 0.4).toFixed(2)}s`,
    duration: `${(1.8 + Math.random() * 1.2).toFixed(2)}s`,
    color: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
    left: `${Math.round(Math.random() * 100)}%`,
  }));
}

/** A self-dismissing celebration banner for a finished game - confetti
 * for a win/draw, a quieter tone for a loss, auto-hides after a few
 * seconds (or on click) so it never permanently blocks the final board
 * position behind it. */
export function CelebrationOverlay({
  headline,
  subtext,
  emoji,
  festive,
  onDismiss,
}: {
  headline: string;
  subtext: string;
  emoji: string;
  festive: boolean;
  onDismiss: () => void;
}) {
  const [visible, setVisible] = useState(true);
  const confetti = useMemo(() => (festive ? makeConfetti(28) : []), [festive]);

  useEffect(() => {
    const timer = window.setTimeout(() => setVisible(false), 4200);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!visible) {
      const t = window.setTimeout(onDismiss, 250);
      return () => window.clearTimeout(t);
    }
  }, [visible, onDismiss]);

  return (
    <div
      className={`pointer-events-none absolute inset-0 z-10 overflow-hidden transition-opacity duration-250 ${
        visible ? "opacity-100" : "opacity-0"
      }`}
    >
      {confetti.map((piece) => (
        <span
          key={piece.id}
          className="animate-confetti-fall absolute top-0 h-2.5 w-1.5 rounded-sm"
          style={
            {
              left: piece.left,
              backgroundColor: piece.color,
              "--x": piece.x,
              "--rotate": piece.rotate,
              "--delay": piece.delay,
              "--duration": piece.duration,
            } as React.CSSProperties
          }
          aria-hidden
        />
      ))}

      <button
        type="button"
        onClick={() => setVisible(false)}
        className="pointer-events-auto absolute inset-0 flex items-center justify-center bg-black/35"
        aria-label="Dismiss"
      >
        <div className="animate-celebration-pop mx-4 flex flex-col items-center gap-1.5 rounded-[var(--radius-lg)] border border-white/15 bg-[#17122b]/90 px-8 py-6 text-center shadow-[0_0_40px_rgba(139,92,246,0.35)]">
          <span className="text-5xl">{emoji}</span>
          <h3 className="text-xl font-extrabold text-white">{headline}</h3>
          <p className="text-[13px] text-white/70">{subtext}</p>
        </div>
      </button>
    </div>
  );
}
