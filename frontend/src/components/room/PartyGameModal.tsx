"use client";

import { Crown, SkipForward, Trophy, X } from "lucide-react";
import { Avatar } from "@/components/ui/Avatar";
import { CountdownBar } from "@/components/ui/CountdownBar";
import { useRoomStore } from "@/lib/store";
import { PARTY_GAME_REGISTRY } from "@/lib/partyGameRegistry";
import { DraftCard } from "@/lib/types";

type SendFn = (type: string, data?: Record<string, unknown>) => void;

export function PartyGameModal({
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
  const game = useRoomStore((s) => s.myPartyGame);

  if (!open || !game) return null;

  const { emoji, label } = PARTY_GAME_REGISTRY[game.kind];
  const isHost = game.hostMemberId === myMemberId;
  const amParticipant = game.participantIds.includes(myMemberId);
  const haveAnswered = game.myAnswer !== null;

  function handleFire(choiceIndex: number) {
    send("party_action", { party_game_id: game!.partyGameId, choice_index: choiceIndex });
  }

  function handlePick(cardId: string) {
    send("party_action", { party_game_id: game!.partyGameId, card_id: cardId });
  }

  function handleJoin() {
    send("join_party_game", { party_game_id: game!.partyGameId });
  }

  function handleLeave() {
    send("leave_party_game", { party_game_id: game!.partyGameId });
  }

  function handleBegin() {
    send("begin_party_game", { party_game_id: game!.partyGameId });
  }

  function handleSkip() {
    send("skip_party_round", { party_game_id: game!.partyGameId });
  }

  function handlePlayAgain() {
    send("start_party_game", { kind: game!.kind });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
      <div
        data-testid="party-game-modal"
        data-phase={game.status === "lobby" ? "lobby" : game.status === "finished" ? "finished" : game.phase}
        className="relative flex max-h-[92vh] w-full max-w-lg flex-col overflow-hidden rounded-[var(--radius-lg)] border border-violet-500/20 bg-gradient-to-b from-[#1b1538] to-[#0d0a1c] text-white shadow-[0_0_60px_rgba(124,58,237,0.25)]"
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
            <LobbyView
              game={game}
              myMemberId={myMemberId}
              isHost={isHost}
              amParticipant={amParticipant}
              onJoin={handleJoin}
              onLeave={handleLeave}
              onBegin={handleBegin}
            />
          )}

          {game.status === "active" && game.kind === "trivia" && game.phase === "question" && game.question && (
            <QuestionView
              game={game}
              myMemberId={myMemberId}
              isHost={isHost}
              haveAnswered={haveAnswered}
              onFire={handleFire}
              onSkip={handleSkip}
            />
          )}

          {game.status === "active" &&
            game.kind === "trivia" &&
            game.phase === "reveal" &&
            "correct_index" in (game.question ?? {}) && <RevealView game={game} myMemberId={myMemberId} />}

          {game.status === "active" && game.kind === "draft" && (game.phase === "picking" || game.phase === "reveal") && (
            <DraftPickView
              game={game}
              myMemberId={myMemberId}
              isHost={isHost}
              onPick={handlePick}
              onSkip={handleSkip}
            />
          )}

          {game.status === "active" && game.kind === "draft" && game.phase === "scoring_round_over" && (
            <DraftScoringRoundOverView game={game} myMemberId={myMemberId} />
          )}

          {game.status === "finished" && (
            <FinalView game={game} myMemberId={myMemberId} onPlayAgain={handlePlayAgain} onClose={onClose} />
          )}
        </div>
      </div>
    </div>
  );
}

function ScoreList({
  rows,
  myMemberId,
}: {
  rows: { member_id: string; name: string; score: number; round_points: number | null; answered: boolean }[];
  myMemberId: string;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      {rows.map((row, i) => (
        <div
          key={row.member_id}
          className="flex items-center gap-2 rounded-[var(--radius-md)] border border-white/10 bg-white/5 px-2.5 py-1.5"
        >
          <span className="w-4 shrink-0 text-center text-[11px] font-bold text-white/40">{i + 1}</span>
          <Avatar name={row.name} seed={row.member_id} size="sm" />
          <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-white">
            {row.name} {row.member_id === myMemberId && <span className="text-violet-300">(you)</span>}
          </span>
          {row.answered && row.round_points === null && (
            <span className="text-[10px] font-semibold uppercase tracking-wide text-emerald-300">answered</span>
          )}
          {row.round_points !== null && (
            <span className={`text-[11px] font-bold ${row.round_points > 0 ? "text-emerald-300" : "text-white/30"}`}>
              +{row.round_points}
            </span>
          )}
          <span className="text-[13px] font-bold text-white">{row.score}</span>
        </div>
      ))}
    </div>
  );
}

function LobbyView({
  game,
  myMemberId,
  isHost,
  amParticipant,
  onJoin,
  onLeave,
  onBegin,
}: {
  game: NonNullable<ReturnType<typeof useRoomStore.getState>["myPartyGame"]>;
  myMemberId: string;
  isHost: boolean;
  amParticipant: boolean;
  onJoin: () => void;
  onLeave: () => void;
  onBegin: () => void;
}) {
  return (
    <div className="flex flex-col gap-4">
      <p className="text-center text-[13px] text-white/60">
        Waiting for players - {game.participantIds.length} joined
      </p>
      <ScoreList rows={game.scoreboard} myMemberId={myMemberId} />
      <div className="flex gap-2">
        {amParticipant ? (
          <button
            type="button"
            onClick={onLeave}
            className="flex-1 rounded-full border border-white/15 py-2.5 text-[13px] font-semibold text-white/70 hover:bg-white/10"
          >
            Leave
          </button>
        ) : (
          <button
            type="button"
            onClick={onJoin}
            className="flex-1 rounded-full border border-white/15 py-2.5 text-[13px] font-semibold text-white hover:bg-white/10"
          >
            Join
          </button>
        )}
        {isHost && (
          <button
            type="button"
            onClick={onBegin}
            disabled={game.participantIds.length < 2}
            className="flex-1 rounded-full bg-gradient-to-r from-violet-500 to-fuchsia-500 py-2.5 text-[13px] font-bold text-white shadow-[0_0_20px_rgba(217,70,239,0.4)] transition-transform hover:scale-105 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:scale-100"
          >
            Begin now
          </button>
        )}
      </div>
    </div>
  );
}

function QuestionView({
  game,
  myMemberId,
  isHost,
  haveAnswered,
  onFire,
  onSkip,
}: {
  game: NonNullable<ReturnType<typeof useRoomStore.getState>["myPartyGame"]>;
  myMemberId: string;
  isHost: boolean;
  haveAnswered: boolean;
  onFire: (choiceIndex: number) => void;
  onSkip: () => void;
}) {
  const question = game.question!;
  return (
    <div className="flex flex-col gap-4">
      <p className="text-center text-[11px] font-bold uppercase tracking-wide text-violet-300/80">
        Round {game.roundIndex + 1} of {game.totalRounds} · {question.category}
      </p>
      <p className="text-center text-[16px] font-bold text-white">{question.question}</p>
      {game.roundStartedAtMs !== null && game.roundDeadlineMs !== null && (
        <CountdownBar startedAtMs={game.roundStartedAtMs} deadlineMs={game.roundDeadlineMs} />
      )}
      <div className="grid grid-cols-1 gap-2" data-testid="choice-grid">
        {question.choices.map((choice, i) => {
          const picked = game.myAnswer?.choiceIndex === i;
          return (
            <button
              key={i}
              type="button"
              disabled={haveAnswered}
              onClick={() => onFire(i)}
              data-testid={`choice-${i}`}
              data-picked={picked}
              className={`rounded-[var(--radius-md)] border px-3 py-2.5 text-left text-[13px] font-medium transition-colors ${
                picked
                  ? "border-violet-400 bg-violet-500/20 text-white"
                  : "border-white/10 bg-white/5 text-white/80 hover:border-white/20 hover:bg-white/10"
              } ${haveAnswered ? "cursor-default" : "cursor-pointer"}`}
            >
              {choice}
            </button>
          );
        })}
      </div>
      <p className="text-center text-[11px] text-white/40" data-testid="answered-count">
        {game.answeredMemberIds.length}/{game.participantIds.length} answered
      </p>
      <ScoreList rows={game.scoreboard} myMemberId={myMemberId} />
      {isHost && (
        <button
          type="button"
          onClick={onSkip}
          className="flex items-center justify-center gap-1.5 self-center rounded-full border border-white/15 px-4 py-2 text-[12px] font-semibold text-white/60 hover:bg-white/10"
        >
          <SkipForward size={13} />
          Skip round
        </button>
      )}
    </div>
  );
}

function RevealView({
  game,
  myMemberId,
}: {
  game: NonNullable<ReturnType<typeof useRoomStore.getState>["myPartyGame"]>;
  myMemberId: string;
}) {
  const question = game.question as { question: string; choices: string[]; correct_index: number };
  return (
    <div className="flex flex-col gap-4">
      <p className="text-center text-[11px] font-bold uppercase tracking-wide text-emerald-300/80">
        Round {game.roundIndex + 1} of {game.totalRounds} - Reveal
      </p>
      <p className="text-center text-[16px] font-bold text-white">{question.question}</p>
      <div className="grid grid-cols-1 gap-2">
        {question.choices.map((choice, i) => {
          const isCorrect = i === question.correct_index;
          return (
            <div
              key={i}
              className={`rounded-[var(--radius-md)] border px-3 py-2.5 text-[13px] font-medium ${
                isCorrect
                  ? "border-emerald-400 bg-emerald-500/20 text-white"
                  : "border-white/10 bg-white/5 text-white/50"
              }`}
            >
              {choice}
            </div>
          );
        })}
      </div>
      <ScoreList rows={game.scoreboard} myMemberId={myMemberId} />
      <p className="text-center text-[12px] text-white/40">Next round coming up...</p>
    </div>
  );
}

function FinalView({
  game,
  myMemberId,
  onPlayAgain,
  onClose,
}: {
  game: NonNullable<ReturnType<typeof useRoomStore.getState>["myPartyGame"]>;
  myMemberId: string;
  onPlayAgain: () => void;
  onClose: () => void;
}) {
  const winner = game.scoreboard[0];
  return (
    <div className="flex flex-col items-center gap-4">
      <Trophy size={36} className="text-amber-300" />
      {winner && (
        <p className="text-center text-[15px] font-bold text-white">
          {winner.name} wins with {winner.score} points!
        </p>
      )}
      <ScoreList rows={game.scoreboard} myMemberId={myMemberId} />
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onClose}
          className="rounded-full border border-white/15 px-5 py-2.5 text-[13px] font-semibold text-white/70 hover:bg-white/10"
        >
          Close
        </button>
        <button
          type="button"
          onClick={onPlayAgain}
          className="flex items-center gap-1.5 rounded-full bg-gradient-to-r from-violet-500 to-fuchsia-500 px-5 py-2.5 text-[13px] font-bold text-white shadow-[0_0_20px_rgba(217,70,239,0.4)] transition-transform hover:scale-105"
        >
          <Crown size={14} />
          Play Again
        </button>
      </div>
    </div>
  );
}

const CARD_COLOR_CLASSES: Record<string, string> = {
  Red: "bg-rose-500 text-white",
  Blue: "bg-blue-500 text-white",
  Green: "bg-emerald-500 text-white",
  Yellow: "bg-amber-400 text-[#1a1a1a]",
  Purple: "bg-violet-500 text-white",
};

function CardChip({ card, dimmed }: { card: DraftCard; dimmed?: boolean }) {
  return (
    <span
      className={`flex h-10 w-8 shrink-0 flex-col items-center justify-center rounded-[4px] text-[13px] font-bold leading-none ${
        CARD_COLOR_CLASSES[card.color] ?? "bg-white/20 text-white"
      } ${dimmed ? "opacity-40" : ""}`}
    >
      {card.value}
    </span>
  );
}

function DraftPickView({
  game,
  myMemberId,
  isHost,
  onPick,
  onSkip,
}: {
  game: NonNullable<ReturnType<typeof useRoomStore.getState>["myPartyGame"]>;
  myMemberId: string;
  isHost: boolean;
  onPick: (cardId: string) => void;
  onSkip: () => void;
}) {
  const havePicked = game.myPick !== null;
  const isReveal = game.phase === "reveal";
  return (
    <div className="flex flex-col gap-4">
      <p className="text-center text-[11px] font-bold uppercase tracking-wide text-violet-300/80">
        Round {(game.scoringRound ?? 0) + 1} of {game.numScoringRounds} · Pick {(game.pickInRound ?? 0) + 1} of{" "}
        {game.handSize}
      </p>

      {isReveal && game.revealedPicks && (
        <div className="flex flex-col gap-1.5 rounded-[var(--radius-md)] border border-emerald-400/30 bg-emerald-500/10 p-3">
          {Object.entries(game.revealedPicks).map(([memberId, card]) => {
            const name = game.scoreboard.find((r) => r.member_id === memberId)?.name ?? "Someone";
            return (
              <div key={memberId} className="flex items-center gap-2">
                <CardChip card={card} />
                <span className="text-[12px] text-emerald-200">
                  {name} {memberId === myMemberId && "(you)"} picked a {card.value} {card.color}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {!isReveal && (
        <>
          <p className="text-center text-[12px] text-white/50">Pick one card from your hand</p>
          <div className="flex flex-wrap justify-center gap-2" data-testid="draft-hand">
            {(game.myHand ?? []).map((card) => (
              <button
                key={card.id}
                type="button"
                disabled={havePicked}
                onClick={() => onPick(card.id)}
                data-testid="draft-card"
                data-card-id={card.id}
                data-picked={game.myPick?.id === card.id}
                className={`rounded-[4px] transition-transform ${
                  game.myPick?.id === card.id ? "scale-110 ring-2 ring-violet-400" : "hover:scale-105"
                } ${havePicked ? "cursor-default" : "cursor-pointer"}`}
              >
                <CardChip card={card} dimmed={havePicked && game.myPick?.id !== card.id} />
              </button>
            ))}
          </div>
          <p className="text-center text-[11px] text-white/40" data-testid="picked-count">
            {game.answeredMemberIds.length}/{game.participantIds.length} picked
          </p>
        </>
      )}

      {game.myCollected && game.myCollected.length > 0 && (
        <div>
          <p className="mb-1 text-center text-[10px] uppercase tracking-wide text-white/40">Your collection</p>
          <div className="flex flex-wrap justify-center gap-1">
            {game.myCollected.map((card) => (
              <CardChip key={card.id} card={card} />
            ))}
          </div>
        </div>
      )}

      <ScoreList rows={game.scoreboard} myMemberId={myMemberId} />
      {isHost && !isReveal && (
        <button
          type="button"
          onClick={onSkip}
          className="flex items-center justify-center gap-1.5 self-center rounded-full border border-white/15 px-4 py-2 text-[12px] font-semibold text-white/60 hover:bg-white/10"
        >
          <SkipForward size={13} />
          Skip pick
        </button>
      )}
    </div>
  );
}

function DraftScoringRoundOverView({
  game,
  myMemberId,
}: {
  game: NonNullable<ReturnType<typeof useRoomStore.getState>["myPartyGame"]>;
  myMemberId: string;
}) {
  const results = game.roundResults ?? {};
  return (
    <div className="flex flex-col gap-4">
      <p className="text-center text-[11px] font-bold uppercase tracking-wide text-emerald-300/80">
        Round {(game.scoringRound ?? 0) + 1} of {game.numScoringRounds} complete!
      </p>
      <div className="flex flex-col gap-2">
        {Object.entries(results).map(([memberId, result]) => {
          const name = game.scoreboard.find((r) => r.member_id === memberId)?.name ?? "Someone";
          return (
            <div key={memberId} className="rounded-[var(--radius-md)] border border-white/10 bg-white/5 p-2.5">
              <p className="mb-1.5 text-[12px] font-semibold text-white">
                {name} {memberId === myMemberId && <span className="text-emerald-300">(you)</span>} · +{result.score}
              </p>
              <div className="flex flex-wrap gap-1">
                {result.collected.map((card) => (
                  <CardChip key={card.id} card={card} />
                ))}
              </div>
            </div>
          );
        })}
      </div>
      <ScoreList rows={game.scoreboard} myMemberId={myMemberId} />
      <p className="text-center text-[12px] text-white/40">Next round coming up...</p>
    </div>
  );
}
