"use client";

import { useEffect, useRef, useState } from "react";
import { Eye, Flag, RotateCcw, Trophy, Volume2, VolumeX, X } from "lucide-react";
import { Avatar } from "@/components/ui/Avatar";
import { useRoomStore, GameState } from "@/lib/store";
import {
  isChessSoundEnabled,
  playCaptureSound,
  playCheckSound,
  playDrawSound,
  playGameStartSound,
  playLoseSound,
  playMoveSound,
  playWinSound,
  setChessSoundEnabled,
} from "@/lib/chessSounds";
import { ChessBoard } from "./ChessBoard";
import { CelebrationOverlay } from "./CelebrationOverlay";
import { LeaderboardPanel } from "./LeaderboardPanel";

type SendFn = (type: string, data?: Record<string, unknown>) => void;

export function GameBoardModal({
  open,
  onClose,
  myMemberId,
  roomId,
  token,
  send,
}: {
  open: boolean;
  onClose: () => void;
  myMemberId: string;
  roomId: string;
  token: string;
  send: SendFn;
}) {
  const game = useRoomStore((s) => s.game);
  const watchingGameId = useRoomStore((s) => s.watchingGameId);
  const watchedGame = useRoomStore((s) => s.watchedGame);

  // A fresh watch_game takes visual priority - it's the action the user
  // just took. Your own game isn't lost, just not the one on screen; the
  // chess icon's badge still gets you back to it.
  const mode: "watch" | "play" = watchingGameId ? "watch" : "play";
  const activeGame: GameState | null = mode === "watch" ? watchedGame : open ? game : null;

  const watcherCount = useRoomStore((s) => s.watcherCounts[activeGame?.gameId ?? ""] ?? 0);

  const [soundOn, setSoundOn] = useState(true);
  const [showLeaderboard, setShowLeaderboard] = useState(false);
  const [showCelebration, setShowCelebration] = useState(false);
  const prevRef = useRef<{ gameId: string; movesLen: number; gameOver: boolean } | null>(null);

  useEffect(() => {
    setSoundOn(isChessSoundEnabled());
  }, []);

  const myColor: "white" | "black" | null =
    activeGame && mode === "play" ? (activeGame.whiteMemberId === myMemberId ? "white" : "black") : null;

  // Sound + celebration triggers - driven purely off state transitions, so
  // this fires the same way whether the move arrived while the modal was
  // open or you reopen it after minimizing (the diff still shows up).
  useEffect(() => {
    if (!activeGame) return;
    const prev = prevRef.current;

    if (!prev || prev.gameId !== activeGame.gameId) {
      if (activeGame.moves.length === 0 && !activeGame.gameOver) playGameStartSound();
      prevRef.current = { gameId: activeGame.gameId, movesLen: activeGame.moves.length, gameOver: activeGame.gameOver };
      if (activeGame.gameOver) setShowCelebration(true);
      return;
    }

    if (activeGame.moves.length > prev.movesLen) {
      if (activeGame.lastMoveWasCapture) playCaptureSound();
      else playMoveSound();
      if (activeGame.inCheck && !activeGame.gameOver) playCheckSound();
    }

    if (activeGame.gameOver && !prev.gameOver) {
      setShowCelebration(true);
      if (mode === "play") {
        if (activeGame.result === "draw") playDrawSound();
        else if (activeGame.result === myColor) playWinSound();
        else playLoseSound();
      }
    }

    prevRef.current = { gameId: activeGame.gameId, movesLen: activeGame.moves.length, gameOver: activeGame.gameOver };
  }, [activeGame, mode, myColor]);

  if (!activeGame) return null;

  const opponentName =
    mode === "play"
      ? myColor === "white"
        ? activeGame.blackName
        : activeGame.whiteName
      : null;
  const opponentId =
    mode === "play" ? (myColor === "white" ? activeGame.blackMemberId : activeGame.whiteMemberId) : null;
  const isMyTurn = mode === "play" && activeGame.turn === myColor;
  const orientation = myColor ?? "white";

  function handleMove(uci: string) {
    const [from, to, promotion] = [uci.slice(0, 2), uci.slice(2, 4), uci.slice(4) || undefined];
    send("game_move", { game_id: activeGame!.gameId, from, to, promotion });
  }

  function handleResign() {
    send("resign_game", { game_id: activeGame!.gameId });
  }

  function handlePlayAgain() {
    if (!opponentId) return;
    send("challenge_to_chess", { opponent_id: opponentId });
    onClose();
  }

  function handleClose() {
    if (mode === "watch") {
      send("unwatch_game", { game_id: activeGame!.gameId });
      useRoomStore.getState().setWatchingGameId(null);
      useRoomStore.getState().setWatchedGame(null);
    } else {
      onClose();
    }
  }

  function toggleSound() {
    const next = !soundOn;
    setChessSoundEnabled(next);
    setSoundOn(next);
  }

  const resultHeadline = (() => {
    if (!activeGame.gameOver) return { emoji: "", headline: "", subtext: "", festive: false };
    if (activeGame.result === "draw") {
      return {
        emoji: "🤝",
        headline: "Draw",
        subtext: (activeGame.termination ?? "").replace(/_/g, " "),
        festive: true,
      };
    }
    const winnerName = activeGame.result === "white" ? activeGame.whiteName : activeGame.blackName;
    if (mode === "play") {
      const iWon = activeGame.result === myColor;
      return {
        emoji: iWon ? "🏆" : "😔",
        headline: iWon ? "You won!" : "You lost",
        subtext: (activeGame.termination ?? "").replace(/_/g, " "),
        festive: iWon,
      };
    }
    return {
      emoji: "🏆",
      headline: `${winnerName} wins!`,
      subtext: (activeGame.termination ?? "").replace(/_/g, " "),
      festive: true,
    };
  })();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
      <div className="relative flex max-h-[92vh] w-full max-w-lg flex-col overflow-hidden rounded-[var(--radius-lg)] border border-violet-500/20 bg-gradient-to-b from-[#1b1538] to-[#0d0a1c] text-white shadow-[0_0_60px_rgba(124,58,237,0.25)]">
        {/* Header */}
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-white/10 bg-white/5 px-4">
          <div className="flex items-center gap-2">
            <span className="text-lg">♟️</span>
            <h2 className="text-[13px] font-extrabold tracking-wide text-white">
              CHESS ARENA
            </h2>
            {mode === "watch" && (
              <span className="flex items-center gap-1 rounded-full bg-rose-500/20 px-2 py-0.5 text-[10px] font-bold text-rose-300">
                <Eye size={10} /> WATCHING
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setShowLeaderboard(true)}
              aria-label="Leaderboard"
              className="flex h-8 w-8 items-center justify-center rounded-full text-amber-300/80 hover:bg-white/10 hover:text-amber-300"
            >
              <Trophy size={16} />
            </button>
            <button
              type="button"
              onClick={toggleSound}
              aria-label={soundOn ? "Mute sound" : "Unmute sound"}
              className="flex h-8 w-8 items-center justify-center rounded-full text-white/60 hover:bg-white/10 hover:text-white"
            >
              {soundOn ? <Volume2 size={16} /> : <VolumeX size={16} />}
            </button>
            <button
              type="button"
              onClick={handleClose}
              aria-label={mode === "watch" ? "Stop watching" : "Minimize game"}
              className="flex h-8 w-8 items-center justify-center rounded-full text-white/60 hover:bg-white/10 hover:text-white"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Player cards */}
        <div className="flex shrink-0 items-center justify-between gap-2 px-4 pt-3.5">
          <PlayerCard
            name={activeGame.whiteName}
            color="white"
            isMe={myColor === "white"}
            active={activeGame.status === "active" && activeGame.turn === "white"}
          />
          <span className="shrink-0 text-[11px] font-black text-white/30">VS</span>
          <PlayerCard
            name={activeGame.blackName}
            color="black"
            isMe={myColor === "black"}
            active={activeGame.status === "active" && activeGame.turn === "black"}
          />
        </div>

        <p className="mt-2 shrink-0 text-center text-[12px] font-medium text-white/60">
          {activeGame.gameOver
            ? "Game over"
            : mode === "play"
              ? isMyTurn
                ? "Your move"
                : `Waiting for ${opponentName}`
              : `${activeGame.turn === "white" ? activeGame.whiteName : activeGame.blackName} to move`}
          {!activeGame.gameOver && activeGame.inCheck && <span className="ml-1.5 font-bold text-rose-400">· Check!</span>}
          {watcherCount > 0 && (
            <span className="ml-1.5 inline-flex items-center gap-1 text-white/40">
              · <Eye size={11} /> {watcherCount} watching
            </span>
          )}
        </p>

        {/* Board */}
        <div className="relative flex-1 overflow-y-auto p-4">
          <ChessBoard
            boardFen={activeGame.boardFen}
            myColor={orientation}
            turn={activeGame.turn}
            legalMoves={activeGame.legalMoves}
            lastMove={activeGame.lastMove}
            inCheck={activeGame.inCheck}
            interactive={mode === "play" && activeGame.status === "active" && isMyTurn}
            onMove={handleMove}
          />

          {showCelebration && activeGame.gameOver && (
            <CelebrationOverlay
              emoji={resultHeadline.emoji}
              headline={resultHeadline.headline}
              subtext={resultHeadline.subtext}
              festive={resultHeadline.festive}
              onDismiss={() => setShowCelebration(false)}
            />
          )}

          {showLeaderboard && (
            <LeaderboardPanel open={showLeaderboard} onClose={() => setShowLeaderboard(false)} roomId={roomId} token={token} />
          )}
        </div>

        {/* Footer */}
        <div className="flex h-16 shrink-0 items-center justify-center gap-3 border-t border-white/10 bg-white/5">
          {mode === "play" && activeGame.status === "active" && (
            <button
              type="button"
              onClick={handleResign}
              className="flex items-center gap-1.5 rounded-full border border-rose-400/40 bg-rose-500/10 px-4 py-2 text-[13px] font-semibold text-rose-300 transition-colors hover:bg-rose-500/20"
            >
              <Flag size={14} />
              Resign
            </button>
          )}
          {mode === "play" && activeGame.gameOver && (
            <button
              type="button"
              onClick={handlePlayAgain}
              className="flex items-center gap-1.5 rounded-full bg-gradient-to-r from-violet-500 to-fuchsia-500 px-5 py-2 text-[13px] font-bold text-white shadow-[0_0_20px_rgba(217,70,239,0.4)] transition-transform hover:scale-105"
            >
              <RotateCcw size={14} />
              Play Again
            </button>
          )}
          {mode === "watch" && (
            <p className="text-[12px] text-white/40">You're spectating - sit back and enjoy the game.</p>
          )}
        </div>
      </div>
    </div>
  );
}

function PlayerCard({
  name,
  color,
  isMe,
  active,
}: {
  name: string;
  color: "white" | "black";
  isMe: boolean;
  active: boolean;
}) {
  return (
    <div
      className={`flex min-w-0 flex-1 items-center gap-2 rounded-[var(--radius-md)] border px-2.5 py-2 transition-all ${
        active
          ? "border-amber-400/60 bg-amber-400/10 shadow-[0_0_14px_rgba(251,191,36,0.25)]"
          : "border-white/10 bg-white/5"
      }`}
    >
      <Avatar name={name} seed={name + color} size="sm" />
      <div className="min-w-0">
        <p className="truncate text-[12px] font-semibold text-white">
          {name} {isMe && <span className="text-violet-300">(you)</span>}
        </p>
        <p className="text-[10px] uppercase tracking-wide text-white/40">{color}</p>
      </div>
    </div>
  );
}
