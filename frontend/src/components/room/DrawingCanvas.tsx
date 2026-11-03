"use client";

import { useEffect, useRef } from "react";
import { Eraser } from "lucide-react";
import { useRoomStore } from "@/lib/store";
import { DrawPoint, WSDrawStroke } from "@/lib/types";

// Fixed internal resolution shared by every client - strokes are
// captured/sent in normalized [0,1] coordinates (relative to each
// client's own rendered CSS size), then scaled against THIS constant
// resolution to render, so two browsers at different window sizes still
// draw the same picture in the same place.
const CANVAS_WIDTH = 600;
const CANVAS_HEIGHT = 400;
const STROKE_COLOR = "#1a1a1a";
const STROKE_WIDTH = 4;
const FLUSH_INTERVAL_MS = 50;

type SendFn = (type: string, data?: Record<string, unknown>) => void;

function drawPolyline(ctx: CanvasRenderingContext2D, points: DrawPoint[], color: string, width: number) {
  if (points.length === 0) return;
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.beginPath();
  ctx.moveTo(points[0].x * CANVAS_WIDTH, points[0].y * CANVAS_HEIGHT);
  for (const p of points.slice(1)) {
    ctx.lineTo(p.x * CANVAS_WIDTH, p.y * CANVAS_HEIGHT);
  }
  ctx.stroke();
}

export function DrawingCanvas({
  partyGameId,
  interactive,
  turnKey,
  send,
}: {
  partyGameId: string;
  interactive: boolean;
  // Changes whenever a new turn begins (e.g. `${turnNumber}`) - clears
  // the canvas locally for everyone the instant a fresh word starts.
  turnKey: string;
  send: SendFn;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const drawEventQueue = useRoomStore((s) => s.drawEventQueue);

  const drawingRef = useRef(false);
  const strokeIdRef = useRef<string | null>(null);
  const pendingPointsRef = useRef<DrawPoint[]>([]);
  const lastSentPointRef = useRef<DrawPoint | null>(null);
  const flushTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Clear the canvas locally whenever a new turn begins.
  useEffect(() => {
    const ctx = canvasRef.current?.getContext("2d");
    if (ctx) ctx.clearRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
  }, [turnKey]);

  // Drain incoming stroke/clear events (same queue-then-clear pattern as
  // callSignalQueue in useVideoCallWebRTC.ts) and paint them.
  useEffect(() => {
    if (drawEventQueue.length === 0) return;
    const ctx = canvasRef.current?.getContext("2d");
    const queued = drawEventQueue;
    useRoomStore.getState().clearDrawEvents();
    if (!ctx) return;
    for (const event of queued) {
      if (event.party_game_id !== partyGameId) continue;
      if (event.type === "draw_clear") {
        ctx.clearRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
      } else {
        const strokeEvent = event as WSDrawStroke;
        drawPolyline(ctx, strokeEvent.points, strokeEvent.color, strokeEvent.width);
      }
    }
  }, [drawEventQueue, partyGameId]);

  function flush() {
    if (pendingPointsRef.current.length === 0 || !strokeIdRef.current) return;
    const points = pendingPointsRef.current;
    pendingPointsRef.current = [];
    lastSentPointRef.current = points[points.length - 1];
    send("draw_stroke", {
      party_game_id: partyGameId,
      stroke_id: strokeIdRef.current,
      points,
      color: STROKE_COLOR,
      width: STROKE_WIDTH,
    });
  }

  function pointFromEvent(e: React.PointerEvent<HTMLCanvasElement>): DrawPoint {
    const rect = e.currentTarget.getBoundingClientRect();
    return {
      x: Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width)),
      y: Math.min(1, Math.max(0, (e.clientY - rect.top) / rect.height)),
    };
  }

  function handlePointerDown(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!interactive) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    drawingRef.current = true;
    strokeIdRef.current = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const point = pointFromEvent(e);
    lastSentPointRef.current = null;
    pendingPointsRef.current = [point];

    const ctx = canvasRef.current?.getContext("2d");
    if (ctx) drawPolyline(ctx, [point, point], STROKE_COLOR, STROKE_WIDTH);

    flushTimerRef.current = setInterval(flush, FLUSH_INTERVAL_MS);
  }

  function handlePointerMove(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!interactive || !drawingRef.current) return;
    const point = pointFromEvent(e);
    const ctx = canvasRef.current?.getContext("2d");
    const prev =
      pendingPointsRef.current[pendingPointsRef.current.length - 1] ?? lastSentPointRef.current ?? point;
    if (ctx) drawPolyline(ctx, [prev, point], STROKE_COLOR, STROKE_WIDTH);
    pendingPointsRef.current.push(point);
  }

  function endStroke() {
    if (!drawingRef.current) return;
    drawingRef.current = false;
    if (flushTimerRef.current) {
      clearInterval(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    flush();
    strokeIdRef.current = null;
  }

  useEffect(() => {
    return () => {
      if (flushTimerRef.current) clearInterval(flushTimerRef.current);
    };
  }, []);

  function handleClear() {
    const ctx = canvasRef.current?.getContext("2d");
    if (ctx) ctx.clearRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
    send("draw_clear", { party_game_id: partyGameId });
  }

  return (
    <div className="flex flex-col items-center gap-2">
      <canvas
        ref={canvasRef}
        width={CANVAS_WIDTH}
        height={CANVAS_HEIGHT}
        data-testid="drawing-canvas"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={endStroke}
        onPointerLeave={endStroke}
        className={`w-full max-w-full rounded-[var(--radius-md)] border border-white/15 bg-white ${
          interactive ? "cursor-crosshair touch-none" : "cursor-default"
        }`}
        style={{ aspectRatio: `${CANVAS_WIDTH} / ${CANVAS_HEIGHT}` }}
      />
      {interactive && (
        <button
          type="button"
          onClick={handleClear}
          data-testid="drawing-clear-button"
          className="flex items-center gap-1.5 self-center rounded-full border border-white/15 px-3 py-1.5 text-[11px] font-semibold text-white/60 hover:bg-white/10"
        >
          <Eraser size={12} />
          Clear
        </button>
      )}
    </div>
  );
}
