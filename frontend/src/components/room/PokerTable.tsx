"use client";

import { useState } from "react";
import { Trophy, X } from "lucide-react";
import { Avatar } from "@/components/ui/Avatar";
import { useRoomStore, CardActiveSeat } from "@/lib/store";
import { CARD_GAME_REGISTRY } from "@/lib/cardGameRegistry";
import { PokerActionKind } from "@/lib/types";

type SendFn = (type: string, data?: Record<string, unknown>) => void;

const SUIT_GLYPH: Record<string, string> = { h: "♥", d: "♦", c: "♣", s: "♠" };
const RED_SUITS = new Set(["h", "d"]);

function PokerCard({ card, faceDown }: { card?: string | null; faceDown?: boolean }) {
  if (faceDown || !card) {
    return (
      <span className="flex h-11 w-8 shrink-0 items-center justify-center rounded-[4px] border border-white/15 bg-gradient-to-br from-indigo-700 to-indigo-900 text-[10px] text-white/30">
        ?
      </span>
    );
  }
  const rank = card[0];
  const suit = card[1];
  const red = RED_SUITS.has(suit);
  return (
    <span
      className={`flex h-11 w-8 shrink-0 flex-col items-center justify-center rounded-[4px] border border-black/10 bg-white text-[13px] font-bold leading-none ${
        red ? "text-rose-600" : "text-[#1a1a1a]"
      }`}
    >
      <span>{rank}</span>
      <span className="text-[11px]">{SUIT_GLYPH[suit]}</span>
    </span>
  );
}

export function PokerTable({
  open,
  onClose,
  myMemberId,
  send,
}: {
  open: boolean;
  onClose: () => void;
  myMemberId: string;
  send: SendFn;
}) {
  const game = useRoomStore((s) => s.myCardGame);
  const [raiseTo, setRaiseTo] = useState<number | null>(null);

  if (!open || !game) return null;

  const { emoji, label } = CARD_GAME_REGISTRY[game.kind];
  const isHost = game.hostMemberId === myMemberId;
  const amParticipant = game.participantIds.includes(myMemberId);

  function act(action: PokerActionKind, extra?: Record<string, unknown>) {
    send("card_action", { card_game_id: game!.cardGameId, action, ...extra });
    setRaiseTo(null);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
      <div
        data-testid="poker-table"
        data-status={game.status}
        data-phase={game.status === "active" ? game.phase : game.status}
        className="relative flex max-h-[92vh] w-full max-w-xl flex-col overflow-hidden rounded-[var(--radius-lg)] border border-emerald-500/20 bg-gradient-to-b from-[#0f2e1f] to-[#071712] text-white shadow-[0_0_60px_rgba(16,185,129,0.2)]"
      >
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-white/10 bg-white/5 px-4">
          <div className="flex items-center gap-2">
            <span className="text-lg">{emoji}</span>
            <h2 className="text-[13px] font-extrabold tracking-wide text-white">{label.toUpperCase()}</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Minimize"
            className="flex h-8 w-8 items-center justify-center rounded-full text-white/60 hover:bg-white/10 hover:text-white"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {game.status === "lobby" && (
            <LobbyView game={game} myMemberId={myMemberId} isHost={isHost} amParticipant={amParticipant} send={send} />
          )}

          {game.status === "active" && game.phase !== "lobby" && (
            <ActiveTableView
              game={game}
              myMemberId={myMemberId}
              raiseTo={raiseTo}
              onRaiseToChange={setRaiseTo}
              onAct={act}
              onNextHand={() => send("start_next_hand", { card_game_id: game.cardGameId })}
            />
          )}

          {game.status === "finished" && (
            <FinalView game={game} onPlayAgain={() => send("start_card_game", { kind: game.kind })} onClose={onClose} />
          )}
        </div>
      </div>
    </div>
  );
}

function LobbyView({
  game,
  myMemberId,
  isHost,
  amParticipant,
  send,
}: {
  game: { cardGameId: string; seats: { memberId: string; name: string }[] };
  myMemberId: string;
  isHost: boolean;
  amParticipant: boolean;
  send: SendFn;
}) {
  return (
    <div className="flex flex-col gap-4">
      <p className="text-center text-[13px] text-white/60">Waiting for players - {game.seats.length} seated</p>
      <div className="flex flex-col gap-1.5">
        {game.seats.map((seat) => (
          <div key={seat.memberId} className="flex items-center gap-2 rounded-[var(--radius-md)] border border-white/10 bg-white/5 px-2.5 py-1.5">
            <Avatar name={seat.name} seed={seat.memberId} size="sm" />
            <span className="text-[13px] font-medium text-white">
              {seat.name} {seat.memberId === myMemberId && <span className="text-emerald-300">(you)</span>}
            </span>
          </div>
        ))}
      </div>
      <div className="flex gap-2">
        {amParticipant ? (
          <button
            type="button"
            onClick={() => send("leave_card_game", { card_game_id: game.cardGameId })}
            className="flex-1 rounded-full border border-white/15 py-2.5 text-[13px] font-semibold text-white/70 hover:bg-white/10"
          >
            Leave
          </button>
        ) : (
          <button
            type="button"
            onClick={() => send("join_card_game", { card_game_id: game.cardGameId })}
            className="flex-1 rounded-full border border-white/15 py-2.5 text-[13px] font-semibold text-white hover:bg-white/10"
          >
            Take a seat
          </button>
        )}
        {isHost && (
          <button
            type="button"
            onClick={() => send("begin_card_game", { card_game_id: game.cardGameId })}
            disabled={game.seats.length < 2}
            className="flex-1 rounded-full bg-gradient-to-r from-emerald-500 to-teal-500 py-2.5 text-[13px] font-bold text-white shadow-[0_0_20px_rgba(16,185,129,0.4)] transition-transform hover:scale-105 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:scale-100"
          >
            Deal first hand
          </button>
        )}
      </div>
    </div>
  );
}

function SeatCard({ seat, isMe, isActing }: { seat: CardActiveSeat; isMe: boolean; isActing: boolean }) {
  return (
    <div
      data-testid="poker-seat"
      data-member-id={seat.memberId}
      data-chips={seat.chips}
      data-hole-cards-visible={seat.holeCards !== null}
      className={`flex flex-col gap-1.5 rounded-[var(--radius-md)] border p-2.5 ${
        isActing ? "border-amber-400/60 bg-amber-400/10 shadow-[0_0_14px_rgba(251,191,36,0.25)]" : "border-white/10 bg-white/5"
      } ${seat.folded ? "opacity-40" : ""}`}
    >
      <div className="flex items-center gap-2">
        <Avatar name={seat.name} seed={seat.memberId} size="sm" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[12px] font-semibold text-white">
            {seat.name} {isMe && <span className="text-emerald-300">(you)</span>}
          </p>
          <p className="text-[10px] text-white/50">
            {seat.chips} chips{seat.allIn && " · ALL IN"}
            {seat.sittingOut && " · sitting out"}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-1">
        <PokerCard card={seat.holeCards?.[0]} faceDown={!seat.holeCards} />
        <PokerCard card={seat.holeCards?.[1]} faceDown={!seat.holeCards} />
        {seat.betThisStreet > 0 && (
          <span className="ml-auto rounded-full bg-white/10 px-2 py-0.5 text-[11px] font-bold text-white">
            {seat.betThisStreet}
          </span>
        )}
      </div>
      {seat.handDescription && <p className="text-[10px] font-medium text-emerald-300">{seat.handDescription}</p>}
    </div>
  );
}

function ActiveTableView({
  game,
  myMemberId,
  raiseTo,
  onRaiseToChange,
  onAct,
  onNextHand,
}: {
  game: {
    cardGameId: string;
    phase: string;
    handNumber: number;
    communityCards: string[];
    pot: number;
    actionOn: string | null;
    seats: CardActiveSeat[];
    myLegalActions: { actions: PokerActionKind[]; callAmount: number; minRaiseTo: number | null; maxRaiseTo: number | null };
    potSummary: { amount: number; winners: string[]; eligible: string[] }[] | null;
  };
  myMemberId: string;
  raiseTo: number | null;
  onRaiseToChange: (v: number | null) => void;
  onAct: (action: PokerActionKind, extra?: Record<string, unknown>) => void;
  onNextHand: () => void;
}) {
  const isMyTurn = game.actionOn === myMemberId;
  const handOver = game.phase === "hand_over" || game.phase === "showdown";
  const legal = game.myLegalActions;
  const canRaise = legal.actions.includes("raise") && legal.minRaiseTo !== null && legal.maxRaiseTo !== null;
  const effectiveRaiseTo = raiseTo ?? legal.minRaiseTo ?? 0;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-center text-[11px] font-bold uppercase tracking-wide text-emerald-300/80">
        Hand #{game.handNumber} · {game.phase.replace("_", " ")}
      </p>

      <div className="flex flex-col items-center gap-2 rounded-[var(--radius-md)] border border-white/10 bg-black/20 py-4">
        <div className="flex gap-1.5">
          {game.communityCards.length === 0 && <p className="text-[11px] text-white/30">No community cards yet</p>}
          {game.communityCards.map((c, i) => (
            <PokerCard key={i} card={c} />
          ))}
        </div>
        <p className="text-[13px] font-bold text-white">Pot: {game.pot}</p>
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {game.seats.map((seat) => (
          <SeatCard key={seat.memberId} seat={seat} isMe={seat.memberId === myMemberId} isActing={seat.memberId === game.actionOn} />
        ))}
      </div>

      {handOver && game.potSummary && (
        <div className="flex flex-col gap-1.5 rounded-[var(--radius-md)] border border-emerald-400/30 bg-emerald-500/10 p-3">
          {game.potSummary.map((p, i) => (
            <p key={i} className="text-center text-[12px] text-emerald-200">
              Pot of {p.amount} won by {p.winners.map((w) => game.seats.find((s) => s.memberId === w)?.name ?? w).join(", ")}
            </p>
          ))}
        </div>
      )}

      {handOver ? (
        <button
          type="button"
          data-testid="next-hand-button"
          onClick={onNextHand}
          className="self-center rounded-full bg-gradient-to-r from-emerald-500 to-teal-500 px-5 py-2.5 text-[13px] font-bold text-white shadow-[0_0_20px_rgba(16,185,129,0.4)] transition-transform hover:scale-105"
        >
          Next Hand
        </button>
      ) : isMyTurn ? (
        <div className="flex flex-col gap-2">
          {canRaise && (
            <div className="flex items-center gap-2">
              <input
                type="range"
                data-testid="raise-slider"
                min={legal.minRaiseTo ?? 0}
                max={legal.maxRaiseTo ?? 0}
                value={effectiveRaiseTo}
                onChange={(e) => onRaiseToChange(Number(e.target.value))}
                className="flex-1"
              />
              <span className="w-14 text-right text-[12px] font-bold text-white">{effectiveRaiseTo}</span>
            </div>
          )}
          <div className="flex gap-2">
            {legal.actions.includes("fold") && (
              <button type="button" data-testid="fold-button" onClick={() => onAct("fold")} className="flex-1 rounded-full border border-rose-400/40 bg-rose-500/10 py-2.5 text-[13px] font-semibold text-rose-300 hover:bg-rose-500/20">
                Fold
              </button>
            )}
            {legal.actions.includes("check") && (
              <button type="button" data-testid="check-button" onClick={() => onAct("check")} className="flex-1 rounded-full border border-white/15 py-2.5 text-[13px] font-semibold text-white hover:bg-white/10">
                Check
              </button>
            )}
            {legal.actions.includes("call") && (
              <button type="button" data-testid="call-button" onClick={() => onAct("call")} className="flex-1 rounded-full border border-white/15 py-2.5 text-[13px] font-semibold text-white hover:bg-white/10">
                Call {legal.callAmount}
              </button>
            )}
            {canRaise && (
              <button
                type="button"
                data-testid="raise-button"
                onClick={() => onAct("raise", { to: effectiveRaiseTo })}
                className="flex-1 rounded-full bg-gradient-to-r from-emerald-500 to-teal-500 py-2.5 text-[13px] font-bold text-white shadow-[0_0_20px_rgba(16,185,129,0.4)]"
              >
                Raise to {effectiveRaiseTo}
              </button>
            )}
          </div>
        </div>
      ) : (
        <p className="text-center text-[12px] text-white/40">
          Waiting for {game.seats.find((s) => s.memberId === game.actionOn)?.name ?? "the next player"}...
        </p>
      )}
    </div>
  );
}

function FinalView({
  game,
  onPlayAgain,
  onClose,
}: {
  game: { seats: { memberId: string; name: string; chips?: number }[] };
  onPlayAgain: () => void;
  onClose: () => void;
}) {
  return (
    <div className="flex flex-col items-center gap-4">
      <Trophy size={36} className="text-amber-300" />
      <p className="text-center text-[15px] font-bold text-white">The table has finished!</p>
      <div className="flex gap-2">
        <button type="button" onClick={onClose} className="rounded-full border border-white/15 px-5 py-2.5 text-[13px] font-semibold text-white/70 hover:bg-white/10">
          Close
        </button>
        <button
          type="button"
          onClick={onPlayAgain}
          className="flex items-center gap-1.5 rounded-full bg-gradient-to-r from-emerald-500 to-teal-500 px-5 py-2.5 text-[13px] font-bold text-white shadow-[0_0_20px_rgba(16,185,129,0.4)] transition-transform hover:scale-105"
        >
          <Trophy size={14} />
          Play Again
        </button>
      </div>
    </div>
  );
}
