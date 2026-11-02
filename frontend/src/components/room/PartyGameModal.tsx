"use client";

import { FormEvent, useState } from "react";
import { Crown, RotateCcw, RotateCw, SkipForward, Trophy, X } from "lucide-react";
import { Avatar } from "@/components/ui/Avatar";
import { CountdownBar } from "@/components/ui/CountdownBar";
import { useRoomStore } from "@/lib/store";
import { PARTY_GAME_REGISTRY } from "@/lib/partyGameRegistry";
import { CodenamesLastEvent, CodenamesTeam, CodenamesTeamRoster, DraftCard, UnoCard, UnoColor } from "@/lib/types";

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

  function handleUnoPlay(cardId: string, chosenColor?: UnoColor) {
    send("party_action", {
      party_game_id: game!.partyGameId,
      action: "play",
      card_id: cardId,
      ...(chosenColor ? { chosen_color: chosenColor } : {}),
    });
  }

  function handleUnoDraw() {
    send("party_action", { party_game_id: game!.partyGameId, action: "draw" });
  }

  function handleCodenamesClue(word: string, number: number) {
    send("party_action", { party_game_id: game!.partyGameId, action: "clue", word, number });
  }

  function handleCodenamesGuess(wordId: string) {
    send("party_action", { party_game_id: game!.partyGameId, action: "guess", word_id: wordId });
  }

  function handleCodenamesPass() {
    send("party_action", { party_game_id: game!.partyGameId, action: "pass" });
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

          {game.status === "active" && game.kind === "uno" && (game.phase === "turn" || game.phase === "reveal") && (
            <UnoTurnView
              game={game}
              myMemberId={myMemberId}
              isHost={isHost}
              onPlay={handleUnoPlay}
              onDraw={handleUnoDraw}
              onSkip={handleSkip}
            />
          )}

          {game.status === "active" && game.kind === "uno" && game.phase === "hand_over" && (
            <UnoHandOverView game={game} myMemberId={myMemberId} />
          )}

          {game.status === "active" &&
            game.kind === "codenames" &&
            (game.phase === "clue" || game.phase === "guessing" || game.phase === "reveal") && (
              <CodenamesBoardView
                game={game}
                myMemberId={myMemberId}
                isHost={isHost}
                onGiveClue={handleCodenamesClue}
                onGuess={handleCodenamesGuess}
                onPass={handleCodenamesPass}
                onSkip={handleSkip}
              />
            )}

          {game.status === "finished" && game.kind === "codenames" && (
            <CodenamesFinalView game={game} onPlayAgain={handlePlayAgain} onClose={onClose} />
          )}

          {game.status === "finished" && game.kind !== "codenames" && (
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
        {PARTY_GAME_REGISTRY[game.kind].minParticipants > 2 &&
          ` (need ${PARTY_GAME_REGISTRY[game.kind].minParticipants}+)`}
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
            disabled={game.participantIds.length < PARTY_GAME_REGISTRY[game.kind].minParticipants}
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

const UNO_COLORS: UnoColor[] = ["Red", "Blue", "Green", "Yellow"];

const UNO_COLOR_CLASSES: Record<string, string> = {
  Red: "bg-rose-500 text-white",
  Blue: "bg-blue-500 text-white",
  Green: "bg-emerald-500 text-white",
  Yellow: "bg-amber-400 text-[#1a1a1a]",
  Wild: "bg-gradient-to-br from-rose-500 via-amber-400 to-blue-500 text-white",
};

function unoCardLabel(card: UnoCard): string {
  switch (card.kind) {
    case "number":
      return String(card.value);
    case "skip":
      return "⊘";
    case "reverse":
      return "⇄";
    case "draw2":
      return "+2";
    case "wild":
      return "W";
    case "wild_draw4":
      return "+4";
    default:
      return "?";
  }
}

function canPlayUnoCard(card: UnoCard, activeColor: string | null, top: UnoCard | null): boolean {
  if (!top || !activeColor) return true;
  if (card.color === "Wild") return true;
  if (card.color === activeColor) return true;
  if (card.kind !== "number" && card.kind === top.kind) return true;
  if (card.kind === "number" && top.kind === "number" && card.value === top.value) return true;
  return false;
}

function UnoCardChip({ card, dimmed }: { card: UnoCard; dimmed?: boolean }) {
  return (
    <span
      className={`flex h-12 w-9 shrink-0 flex-col items-center justify-center rounded-[4px] text-[14px] font-bold leading-none ${
        UNO_COLOR_CLASSES[card.color] ?? "bg-white/20 text-white"
      } ${dimmed ? "opacity-40" : ""}`}
    >
      {unoCardLabel(card)}
    </span>
  );
}

function UnoTurnView({
  game,
  myMemberId,
  isHost,
  onPlay,
  onDraw,
  onSkip,
}: {
  game: NonNullable<ReturnType<typeof useRoomStore.getState>["myPartyGame"]>;
  myMemberId: string;
  isHost: boolean;
  onPlay: (cardId: string, chosenColor?: UnoColor) => void;
  onDraw: () => void;
  onSkip: () => void;
}) {
  const [pendingWildCardId, setPendingWildCardId] = useState<string | null>(null);
  const isMyTurn = game.currentPlayerId === myMemberId;
  const isReveal = game.phase === "reveal";
  const currentPlayerName = game.scoreboard.find((r) => r.member_id === game.currentPlayerId)?.name ?? "Someone";

  function handleCardClick(card: UnoCard) {
    if (!isMyTurn || isReveal) return;
    if (!canPlayUnoCard(card, game.activeColor, game.discardTop)) return;
    if (card.color === "Wild") {
      setPendingWildCardId(card.id);
      return;
    }
    onPlay(card.id);
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-center text-[11px] font-bold uppercase tracking-wide text-violet-300/80">
        Hand {game.handNumber} of {game.numHands}
      </p>

      {isReveal && game.lastAction && (
        <div className="rounded-[var(--radius-md)] border border-emerald-400/30 bg-emerald-500/10 p-2.5 text-center text-[12px] text-emerald-200">
          {game.scoreboard.find((r) => r.member_id === game.lastAction!.member_id)?.name ?? "Someone"}
          {game.lastAction.member_id === myMemberId ? " (you) " : " "}
          {game.lastAction.kind === "draw" ? "drew a card" : "played a card"}
        </div>
      )}

      <div className="flex items-center justify-center gap-4">
        <div className="flex flex-col items-center gap-1">
          <p className="text-[10px] uppercase tracking-wide text-white/40">Draw pile</p>
          <span className="flex h-12 w-9 items-center justify-center rounded-[4px] border border-white/20 bg-white/10 text-[12px] font-bold text-white/60">
            {game.drawPileSize}
          </span>
        </div>
        <div className="flex flex-col items-center gap-1">
          <p className="text-[10px] uppercase tracking-wide text-white/40">Discard</p>
          {game.discardTop && <UnoCardChip card={game.discardTop} />}
        </div>
        <div className="flex flex-col items-center gap-1">
          <p className="text-[10px] uppercase tracking-wide text-white/40">Direction</p>
          {game.direction === 1 ? (
            <RotateCw size={18} className="text-white/60" />
          ) : (
            <RotateCcw size={18} className="text-white/60" />
          )}
        </div>
      </div>

      {game.activeColor && (
        <p className="text-center text-[11px] text-white/50">
          Active color:{" "}
          <span className={`rounded px-1.5 py-0.5 ${UNO_COLOR_CLASSES[game.activeColor] ?? ""}`}>{game.activeColor}</span>
        </p>
      )}

      <p className="text-center text-[13px] font-semibold text-white" data-testid="uno-turn-indicator">
        {isMyTurn && !isReveal ? "Your turn!" : `${currentPlayerName}'s turn`}
      </p>

      {pendingWildCardId !== null && (
        <div className="flex flex-col items-center gap-2 rounded-[var(--radius-md)] border border-white/15 bg-white/5 p-3">
          <p className="text-[12px] text-white/70">Choose a color</p>
          <div className="flex gap-2">
            {UNO_COLORS.map((color) => (
              <button
                key={color}
                type="button"
                onClick={() => {
                  onPlay(pendingWildCardId, color);
                  setPendingWildCardId(null);
                }}
                className={`h-9 w-9 rounded-full ${UNO_COLOR_CLASSES[color]} transition-transform hover:scale-110`}
                aria-label={color}
              />
            ))}
          </div>
          <button
            type="button"
            onClick={() => setPendingWildCardId(null)}
            className="text-[11px] text-white/40 hover:text-white/60"
          >
            Cancel
          </button>
        </div>
      )}

      <div className="flex flex-wrap justify-center gap-2" data-testid="uno-hand">
        {(game.unoMyHand ?? []).map((card) => {
          const playable = isMyTurn && !isReveal && canPlayUnoCard(card, game.activeColor, game.discardTop);
          return (
            <button
              key={card.id}
              type="button"
              disabled={!playable}
              onClick={() => handleCardClick(card)}
              data-testid="uno-card"
              data-card-id={card.id}
              className={`rounded-[4px] transition-transform ${playable ? "cursor-pointer hover:scale-110" : "cursor-default"}`}
            >
              <UnoCardChip card={card} dimmed={!playable} />
            </button>
          );
        })}
      </div>

      {isMyTurn && !isReveal && (
        <button
          type="button"
          onClick={onDraw}
          data-testid="uno-draw-button"
          className="self-center rounded-full border border-white/15 px-4 py-2 text-[12px] font-semibold text-white/70 hover:bg-white/10"
        >
          Draw a card
        </button>
      )}

      <div className="flex flex-wrap justify-center gap-1.5 text-[11px] text-white/40">
        {Object.entries(game.handSizes ?? {}).map(([memberId, size]) => {
          if (memberId === myMemberId) return null;
          const name = game.scoreboard.find((r) => r.member_id === memberId)?.name ?? "Someone";
          return (
            <span key={memberId} className="rounded-full border border-white/10 px-2 py-0.5">
              {name}: {size}
            </span>
          );
        })}
      </div>

      <ScoreList rows={game.scoreboard} myMemberId={myMemberId} />
      {isHost && !isReveal && (
        <button
          type="button"
          onClick={onSkip}
          className="flex items-center justify-center gap-1.5 self-center rounded-full border border-white/15 px-4 py-2 text-[12px] font-semibold text-white/60 hover:bg-white/10"
        >
          <SkipForward size={13} />
          Skip turn
        </button>
      )}
    </div>
  );
}

function UnoHandOverView({
  game,
  myMemberId,
}: {
  game: NonNullable<ReturnType<typeof useRoomStore.getState>["myPartyGame"]>;
  myMemberId: string;
}) {
  const result = game.handResult;
  const winnerName = result
    ? game.scoreboard.find((r) => r.member_id === result.winner_member_id)?.name ?? "Someone"
    : null;
  return (
    <div className="flex flex-col gap-4">
      <p className="text-center text-[11px] font-bold uppercase tracking-wide text-emerald-300/80">
        Hand {game.handNumber} of {game.numHands} complete!
      </p>
      {result && (
        <p className="text-center text-[15px] font-bold text-white">
          {winnerName} {result.winner_member_id === myMemberId && "(you)"} went out and wins +{result.points} points!
        </p>
      )}
      <ScoreList rows={game.scoreboard} myMemberId={myMemberId} />
      <p className="text-center text-[12px] text-white/40">Next hand coming up...</p>
    </div>
  );
}

const CODENAMES_TEAM_TEXT_CLASSES: Record<CodenamesTeam, string> = {
  red: "text-rose-300",
  blue: "text-blue-300",
};

const CODENAMES_OWNER_CLASSES: Record<string, string> = {
  red: "bg-rose-600 text-white border-rose-400",
  blue: "bg-blue-600 text-white border-blue-400",
  neutral: "bg-amber-100 text-[#1a1a1a] border-amber-200",
  assassin: "bg-black text-white border-white/40",
};
const CODENAMES_UNKNOWN_CLASS = "bg-white/10 text-white/80 border-white/15";

function codenamesEventText(event: CodenamesLastEvent): string {
  const teamName = event.team === "red" ? "Red" : "Blue";
  switch (event.kind) {
    case "clue_given":
      return `${teamName} gave the clue: "${event.word}" (${event.number})`;
    case "clue_timeout":
      return `${teamName}'s spymaster ran out of time - turn passes`;
    case "guess_pass":
      return `${teamName} passed`;
    case "guess_timeout":
      return `${teamName} ran out of time to guess`;
    case "guess_result": {
      const ownerLabel =
        event.owner === "assassin"
          ? "the assassin!"
          : event.owner === "neutral"
            ? "a neutral word"
            : `${event.owner === "red" ? "Red" : "Blue"}'s word`;
      return `${teamName} guessed "${event.word}" - it was ${ownerLabel}`;
    }
    default:
      return "";
  }
}

function CodenamesTeamPanel({
  team,
  roster,
  activeTeam,
  myMemberId,
  namesByMemberId,
}: {
  team: CodenamesTeam;
  roster: CodenamesTeamRoster;
  activeTeam: CodenamesTeam | null;
  myMemberId: string;
  namesByMemberId: Record<string, string>;
}) {
  const isActive = team === activeTeam;
  return (
    <div
      data-testid={`codenames-team-${team}`}
      className={`flex-1 rounded-[var(--radius-md)] border p-2.5 ${
        isActive
          ? team === "red"
            ? "border-rose-400 bg-rose-500/10"
            : "border-blue-400 bg-blue-500/10"
          : "border-white/10 bg-white/5"
      }`}
    >
      <p className={`mb-1.5 text-[11px] font-bold uppercase tracking-wide ${CODENAMES_TEAM_TEXT_CLASSES[team]}`}>
        {team === "red" ? "Red" : "Blue"} Team {isActive && "· active"}
      </p>
      <p className="truncate text-[12px] text-white/80">
        🕵️ {namesByMemberId[roster.spymaster] ?? "Someone"} {roster.spymaster === myMemberId && "(you)"}
      </p>
      {roster.operatives.map((memberId) => (
        <p key={memberId} className="truncate text-[12px] text-white/60">
          {namesByMemberId[memberId] ?? "Someone"} {memberId === myMemberId && "(you)"}
        </p>
      ))}
    </div>
  );
}

function CodenamesBoard({
  board,
  interactive,
  onGuess,
  size = "md",
}: {
  board: NonNullable<ReturnType<typeof useRoomStore.getState>["myPartyGame"]>["codenamesBoard"];
  interactive: boolean;
  onGuess?: (wordId: string) => void;
  size?: "sm" | "md";
}) {
  return (
    <div className="grid grid-cols-5 gap-1.5" data-testid="codenames-board">
      {(board ?? []).map((card) => {
        const colorClass = card.owner ? CODENAMES_OWNER_CLASSES[card.owner] : CODENAMES_UNKNOWN_CLASS;
        const clickable = interactive && !card.revealed;
        return (
          <button
            key={card.id}
            type="button"
            disabled={!clickable}
            onClick={() => onGuess?.(card.id)}
            data-testid="codenames-word"
            data-card-id={card.id}
            className={`flex items-center justify-center rounded-[4px] border px-1 text-center font-bold leading-tight transition-transform ${
              size === "sm" ? "h-9 text-[8px]" : "h-12 text-[10px]"
            } ${colorClass} ${card.revealed ? "opacity-70" : ""} ${
              clickable ? "cursor-pointer hover:scale-105" : "cursor-default"
            }`}
          >
            {card.word}
          </button>
        );
      })}
    </div>
  );
}

function CodenamesBoardView({
  game,
  myMemberId,
  isHost,
  onGiveClue,
  onGuess,
  onPass,
  onSkip,
}: {
  game: NonNullable<ReturnType<typeof useRoomStore.getState>["myPartyGame"]>;
  myMemberId: string;
  isHost: boolean;
  onGiveClue: (word: string, number: number) => void;
  onGuess: (wordId: string) => void;
  onPass: () => void;
  onSkip: () => void;
}) {
  const [clueWord, setClueWord] = useState("");
  const [clueNumber, setClueNumber] = useState(1);

  const teams = game.codenamesTeams;
  const activeTeam = game.activeTeam;
  const isReveal = game.phase === "reveal";
  const namesByMemberId = Object.fromEntries(game.scoreboard.map((r) => [r.member_id, r.name]));

  const isMySpymasterTurn = game.phase === "clue" && game.myRole === "spymaster" && game.myTeam === activeTeam;
  const isMyGuessingTurn = game.phase === "guessing" && game.myRole === "operative" && game.myTeam === activeTeam;

  function handleGiveClue(e: FormEvent) {
    e.preventDefault();
    const word = clueWord.trim();
    if (!word) return;
    onGiveClue(word, clueNumber);
    setClueWord("");
    setClueNumber(1);
  }

  return (
    <div className="flex flex-col gap-4">
      {teams && (
        <div className="flex gap-2">
          <CodenamesTeamPanel
            team="red"
            roster={teams.red}
            activeTeam={activeTeam}
            myMemberId={myMemberId}
            namesByMemberId={namesByMemberId}
          />
          <CodenamesTeamPanel
            team="blue"
            roster={teams.blue}
            activeTeam={activeTeam}
            myMemberId={myMemberId}
            namesByMemberId={namesByMemberId}
          />
        </div>
      )}

      {isReveal && game.lastEvent && (
        <div
          data-testid="codenames-last-event"
          className="rounded-[var(--radius-md)] border border-emerald-400/30 bg-emerald-500/10 p-2.5 text-center text-[12px] text-emerald-200"
        >
          {codenamesEventText(game.lastEvent)}
        </div>
      )}

      {!isReveal && game.currentClue && (
        <p className="text-center text-[15px] font-bold text-white">
          Clue: {game.currentClue.word} ({game.currentClue.number})
          {game.guessesRemaining !== null && (
            <span className="ml-2 text-[12px] font-normal text-white/50">{game.guessesRemaining} guesses left</span>
          )}
        </p>
      )}

      {game.phase === "clue" && !isMySpymasterTurn && (
        <p className="text-center text-[12px] text-white/50">
          Waiting for {activeTeam === "red" ? "Red" : "Blue"}'s spymaster to give a clue...
        </p>
      )}

      {game.phase === "guessing" && !isMyGuessingTurn && (
        <p className="text-center text-[12px] text-white/50">
          {activeTeam === "red" ? "Red" : "Blue"}'s operatives are guessing...
        </p>
      )}

      {isMySpymasterTurn && (
        <form onSubmit={handleGiveClue} className="flex items-center gap-2" data-testid="codenames-clue-form">
          <input
            value={clueWord}
            onChange={(e) => setClueWord(e.target.value)}
            placeholder="Your clue word"
            maxLength={24}
            autoFocus
            data-testid="codenames-clue-input"
            className="min-w-0 flex-1 rounded-full border border-white/15 bg-white/5 px-3 py-2 text-[13px] text-white placeholder:text-white/30 focus:border-violet-400 focus:outline-none"
          />
          <select
            value={clueNumber}
            onChange={(e) => setClueNumber(Number(e.target.value))}
            data-testid="codenames-clue-number"
            className="rounded-full border border-white/15 bg-white/5 px-2 py-2 text-[13px] text-white focus:border-violet-400 focus:outline-none"
          >
            {Array.from({ length: 10 }, (_, i) => i).map((n) => (
              <option key={n} value={n} className="bg-[#1b1538]">
                {n}
              </option>
            ))}
          </select>
          <button
            type="submit"
            disabled={!clueWord.trim()}
            data-testid="codenames-clue-submit"
            className="shrink-0 rounded-full bg-gradient-to-r from-violet-500 to-fuchsia-500 px-4 py-2 text-[13px] font-bold text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            Give clue
          </button>
        </form>
      )}

      <CodenamesBoard board={game.codenamesBoard} interactive={isMyGuessingTurn} onGuess={onGuess} />

      {isMyGuessingTurn && (
        <button
          type="button"
          onClick={onPass}
          data-testid="codenames-pass-button"
          className="self-center rounded-full border border-white/15 px-4 py-2 text-[12px] font-semibold text-white/70 hover:bg-white/10"
        >
          Pass
        </button>
      )}

      {isHost && !isReveal && (
        <button
          type="button"
          onClick={onSkip}
          className="flex items-center justify-center gap-1.5 self-center rounded-full border border-white/15 px-4 py-2 text-[12px] font-semibold text-white/60 hover:bg-white/10"
        >
          <SkipForward size={13} />
          Skip phase
        </button>
      )}
    </div>
  );
}

function CodenamesFinalView({
  game,
  onPlayAgain,
  onClose,
}: {
  game: NonNullable<ReturnType<typeof useRoomStore.getState>["myPartyGame"]>;
  onPlayAgain: () => void;
  onClose: () => void;
}) {
  const winner = game.winner;
  const namesByMemberId = Object.fromEntries(game.scoreboard.map((r) => [r.member_id, r.name]));
  return (
    <div className="flex flex-col items-center gap-4">
      <Trophy size={36} className={winner === "red" ? "text-rose-300" : "text-blue-300"} />
      <p className="text-center text-[15px] font-bold text-white">
        {winner === "red" ? "Red" : "Blue"} Team wins!{" "}
        <span className="font-normal text-white/50">
          ({game.winReason === "assassin_hit" ? "the other team hit the assassin" : "found all their words"})
        </span>
      </p>
      {game.codenamesTeams && (
        <div className="flex w-full gap-2">
          <CodenamesTeamPanel
            team="red"
            roster={game.codenamesTeams.red}
            activeTeam={winner}
            myMemberId=""
            namesByMemberId={namesByMemberId}
          />
          <CodenamesTeamPanel
            team="blue"
            roster={game.codenamesTeams.blue}
            activeTeam={winner}
            myMemberId=""
            namesByMemberId={namesByMemberId}
          />
        </div>
      )}
      <div className="w-full">
        <CodenamesBoard board={game.codenamesBoard} interactive={false} size="sm" />
      </div>
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
