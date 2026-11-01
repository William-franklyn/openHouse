"use client";

import { useCallback, useEffect, useRef } from "react";
import { wsUrl } from "./api";
import { GameState, useRoomStore } from "./store";
import { WSServerEvent } from "./types";

const MAX_BACKOFF_MS = 15000;
const BASE_BACKOFF_MS = 1000;

type SendFn = (type: string, data?: Record<string, unknown>) => void;

/** Owns the WebSocket connection for one room: auth + resume on connect,
 * dispatches every server event into the Zustand store, and reconnects
 * with exponential backoff (1s, 2s, 4s... capped at 15s) on any
 * unexpected close, per SPEC.md's reconnect requirement. */
export function useRoomSocket(token: string | null): { send: SendFn } {
  const wsRef = useRef<WebSocket | null>(null);
  const attemptRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intentionalCloseRef = useRef(false);
  const tokenRef = useRef(token);
  tokenRef.current = token;

  const dispatchEvent = useCallback((event: WSServerEvent) => {
    const store = useRoomStore.getState();
    switch (event.type) {
      case "ready":
        store.setStatus("open");
        break;
      case "message":
        store.receiveMessage({
          id: event.id,
          channel_id: event.channel_id,
          seq: event.seq,
          member_id: event.member_id,
          from_name: event.from_name,
          kind: event.kind,
          text: event.text,
          file_id: event.file_id,
          created_at: event.created_at,
        });
        break;
      case "message_deleted":
        store.removeMessage(event.channel_id, event.message_id);
        store.removePhotoByMessageId(event.message_id);
        break;
      case "pins":
        store.setPins(event.message_ids);
        break;
      case "presence":
        store.setPresence(event.online);
        break;
      case "member_joined":
      case "member_left":
        // presence (sent alongside these) carries the authoritative roster
        break;
      case "role_changed":
        if (event.member_id === store.myMemberId) store.setMyRole(event.role);
        break;
      case "ownership_offer":
        store.setOwnershipOffer(event.from_name);
        break;
      case "ownership_changed":
        store.applyOwnershipChange(event.new_owner_id);
        break;
      case "channel_created":
        store.addChannel({ id: event.channel_id, name: event.name });
        break;
      case "removed":
        intentionalCloseRef.current = true;
        store.setRemoved(event.reason);
        break;
      case "room_deleted":
        intentionalCloseRef.current = true;
        store.setRoomDeleted(event.message);
        break;
      case "room_ended":
        intentionalCloseRef.current = true;
        store.setRoomEnded();
        break;
      case "error":
        store.setError(event.code, event.message);
        break;
      case "music_started":
        store.setMusic({
          id: event.id,
          source: event.source,
          fileId: event.file_id,
          url: event.url,
          attribution: event.attribution,
          filename: event.filename,
          startedByMemberId: event.started_by_member_id,
          startedByName: event.started_by_name,
          startedAtMs: event.started_at_ms,
        });
        break;
      case "music_stopped":
        store.setMusic(null);
        break;
      case "music_queue_updated":
        store.setMusicQueue(
          event.queue.map((t) => ({
            id: t.id,
            source: t.source,
            fileId: t.file_id,
            url: t.url,
            attribution: t.attribution,
            filename: t.filename,
            requestedByMemberId: t.requested_by_member_id,
            requestedByName: t.requested_by_name,
            queuedAtMs: t.queued_at_ms,
          }))
        );
        break;
      case "music_requested":
        store.setMusicRequestNotice({
          filename: event.filename,
          requestedByName: event.requested_by_name,
        });
        break;
      case "call_presence":
        store.setCallPresence(event.call_id, event.member_ids);
        // Defensive: if presence for my own active call stops including
        // me (stale TTL, server-side cleanup I didn't initiate), don't
        // leave the modal showing a call I'm not actually part of.
        if (event.call_id === store.myCallId && !event.member_ids.includes(store.myMemberId ?? "")) {
          store.setMyCallId(null);
        }
        break;
      case "call_invite":
        if (event.host_member_id === store.myMemberId) {
          // This is the server echoing back the call_id of the meeting I
          // just started - open my own call modal, no popup needed.
          store.setMyCallId(event.call_id);
        } else {
          store.setIncomingCallInvite({
            callId: event.call_id,
            hostMemberId: event.host_member_id,
            hostName: event.host_name,
          });
        }
        break;
      case "call_offer":
      case "call_answer":
      case "ice_candidate":
        store.pushCallSignal(event);
        break;
      case "game_invite":
        if (event.challenger_member_id === store.myMemberId) {
          // The server echoing back my own challenge - show a "waiting
          // for a reply" state, not a toast asking me to accept my own
          // invite. Same self-echo pattern as call_invite.
          store.setPendingChallenge({ gameId: event.game_id, kind: event.kind, opponentName: event.opponent_name });
        } else {
          store.setIncomingGameInvite({
            gameId: event.game_id,
            kind: event.kind,
            challengerMemberId: event.challenger_member_id,
            challengerName: event.challenger_name,
          });
        }
        break;
      case "game_declined":
        if (store.pendingChallenge?.gameId === event.game_id) {
          store.setPendingChallenge(null);
          store.setError("game_declined", "They declined your challenge.");
        }
        break;
      case "game_cancelled":
        if (store.incomingGameInvite?.gameId === event.game_id) {
          store.setIncomingGameInvite(null);
        }
        break;
      case "game_link_waiting":
        store.setLinkWaitingGame({ gameId: event.game_id, kind: event.kind, linkToken: event.link_token });
        break;
      case "game_state": {
        const base = {
          gameId: event.game_id,
          status: event.status,
          whiteMemberId: event.white_member_id,
          whiteName: event.white_name,
          blackMemberId: event.black_member_id,
          blackName: event.black_name,
          moves: event.moves,
          turn: event.turn,
          gameOver: event.game_over,
          result: event.result,
          termination: event.termination,
          lastMove: event.last_move,
        };
        let gameState: GameState;
        if (event.kind === "chess") {
          gameState = {
            ...base,
            kind: "chess",
            boardFen: event.board_fen,
            legalMoves: event.legal_moves,
            inCheck: event.in_check,
            lastMoveWasCapture: event.last_move_was_capture,
          };
        } else if (event.kind === "tictactoe") {
          gameState = { ...base, kind: "tictactoe", board: event.board };
        } else if (event.kind === "connect4") {
          gameState = { ...base, kind: "connect4", board: event.board, legalMoves: event.legal_moves };
        } else if (event.kind === "dots_and_boxes") {
          gameState = {
            ...base,
            kind: "dots_and_boxes",
            hEdges: event.h_edges,
            vEdges: event.v_edges,
            boxes: event.boxes,
          };
        } else if (event.kind === "reversi") {
          gameState = { ...base, kind: "reversi", board: event.board, legalMoves: event.legal_moves };
        } else if (event.kind === "checkers") {
          gameState = {
            ...base,
            kind: "checkers",
            board: event.board,
            mustContinueFrom: event.must_continue_from,
            legalMoves: event.legal_moves,
          };
        } else if (event.kind === "backgammon") {
          gameState = {
            ...base,
            kind: "backgammon",
            points: event.points,
            bar: event.bar as [number, number],
            borneOff: event.borne_off as [number, number],
            dice: event.dice,
            remainingDice: event.remaining_dice,
            legalMoves: event.legal_moves,
          };
        } else {
          gameState = {
            ...base,
            kind: "battleship",
            whiteGrid: event.white_grid,
            blackGrid: event.black_grid,
            shipHits: event.ship_hits,
            shipSizes: event.ship_sizes,
          };
        }
        const amPlayer =
          event.white_member_id === store.myMemberId || event.black_member_id === store.myMemberId;
        if (amPlayer) {
          // Accepting (or any later move) resolves whichever side of the
          // invite flow I was on - all three clear safely even if only
          // one was ever set (targeted invite, or a link someone claimed).
          if (store.pendingChallenge?.gameId === event.game_id) store.setPendingChallenge(null);
          if (store.incomingGameInvite?.gameId === event.game_id) store.setIncomingGameInvite(null);
          if (store.linkWaitingGame?.gameId === event.game_id) store.setLinkWaitingGame(null);
          store.setMyGameId(event.game_id);
          store.setGame(gameState);
        } else {
          // Anyone else receiving game_state only got it because they
          // asked to watch_game - route it to the spectator slot, never
          // the "my own game" one.
          store.setWatchedGame(gameState);
        }
        break;
      }
      case "game_live":
        // Room-wide broadcast reaches the players too (it's unfiltered on
        // the server) - skip it for my own game, myGameId/game already
        // covers that, and I shouldn't see a "spectate" banner for myself.
        if (event.white_member_id !== store.myMemberId && event.black_member_id !== store.myMemberId) {
          store.setLiveGame({
            gameId: event.game_id,
            kind: event.kind,
            whiteMemberId: event.white_member_id,
            whiteName: event.white_name,
            blackMemberId: event.black_member_id,
            blackName: event.black_name,
          });
        }
        break;
      case "game_live_ended":
        store.removeLiveGame(event.game_id);
        if (store.watchingGameId === event.game_id) {
          store.setWatchingGameId(null);
          store.setWatchedGame(null);
        }
        break;
      case "game_watchers":
        store.setWatcherCount(event.game_id, event.count);
        break;
      case "party_state": {
        const base = {
          partyGameId: event.party_game_id,
          kind: event.kind,
          status: event.status,
          hostMemberId: event.host_member_id,
          roundIndex: event.round_index,
          totalRounds: event.total_rounds,
          participantIds: event.participant_ids,
          scoreboard: event.scoreboard,
          phase: event.phase,
        };
        if (event.phase === "question") {
          store.setPartyGame({
            ...base,
            question: event.question,
            roundStartedAtMs: event.round_started_at_ms,
            roundDeadlineMs: event.round_deadline_ms,
            answeredMemberIds: event.answered_member_ids,
            myAnswer: event.my_answer ? { choiceIndex: event.my_answer.choice_index } : null,
            answers: null,
            roundPointsAwarded: null,
          });
        } else if (event.phase === "reveal") {
          store.setPartyGame({
            ...base,
            question: event.question,
            roundStartedAtMs: null,
            roundDeadlineMs: null,
            answeredMemberIds: [],
            myAnswer: null,
            answers: Object.fromEntries(
              Object.entries(event.answers).map(([id, a]) => [
                id,
                { choiceIndex: a.choice_index, answeredAtMs: a.answered_at_ms },
              ])
            ),
            roundPointsAwarded: event.round_points_awarded,
          });
        } else {
          store.setPartyGame({
            ...base,
            question: null,
            roundStartedAtMs: null,
            roundDeadlineMs: null,
            answeredMemberIds: [],
            myAnswer: null,
            answers: null,
            roundPointsAwarded: null,
          });
        }
        break;
      }
      case "party_cancelled":
        if (store.myPartyGame?.partyGameId === event.party_game_id) {
          store.setPartyGame(null);
        }
        break;
      case "photo_shared":
        store.addPhoto({
          file_id: event.file_id,
          message_id: event.message_id,
          filename: event.filename,
          member_id: event.member_id,
          member_name: event.member_name,
          created_at: event.created_at,
        });
        break;
    }
  }, []);

  const connect = useCallback(() => {
    if (!tokenRef.current) return;
    intentionalCloseRef.current = false;
    useRoomStore.getState().setStatus(attemptRef.current === 0 ? "connecting" : "reconnecting");

    const ws = new WebSocket(wsUrl());
    wsRef.current = ws;

    ws.addEventListener("open", () => {
      ws.send(
        JSON.stringify({
          type: "auth",
          session_token: tokenRef.current,
          last_seq: useRoomStore.getState().lastSeqByChannel,
        })
      );
    });

    ws.addEventListener("message", (evt) => {
      let data: WSServerEvent;
      try {
        data = JSON.parse(evt.data);
      } catch {
        return;
      }
      if (data.type === "ready") attemptRef.current = 0;
      dispatchEvent(data);
    });

    ws.addEventListener("close", () => {
      useRoomStore.getState().setStatus("closed");
      if (intentionalCloseRef.current) return;

      const delay = Math.min(BASE_BACKOFF_MS * 2 ** attemptRef.current, MAX_BACKOFF_MS);
      attemptRef.current += 1;
      timerRef.current = setTimeout(connect, delay);
    });
  }, [dispatchEvent]);

  useEffect(() => {
    if (!token) return;
    connect();
    return () => {
      intentionalCloseRef.current = true;
      if (timerRef.current) clearTimeout(timerRef.current);
      wsRef.current?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const send: SendFn = useCallback((type, data) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type, ...data }));
    }
  }, []);

  return { send };
}
