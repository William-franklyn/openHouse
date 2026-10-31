"use client";

import { useCallback, useEffect, useRef } from "react";
import { wsUrl } from "./api";
import { useRoomStore } from "./store";
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
          store.setPendingChallenge({ gameId: event.game_id, opponentName: event.opponent_name });
        } else {
          store.setIncomingGameInvite({
            gameId: event.game_id,
            challengerMemberId: event.challenger_member_id,
            challengerName: event.challenger_name,
          });
        }
        break;
      case "game_declined":
        if (store.pendingChallenge?.gameId === event.game_id) {
          store.setPendingChallenge(null);
          store.setError("game_declined", "They declined your chess challenge.");
        }
        break;
      case "game_cancelled":
        if (store.incomingGameInvite?.gameId === event.game_id) {
          store.setIncomingGameInvite(null);
        }
        break;
      case "game_state":
        // Accepting (or any later move) resolves whichever side of the
        // invite flow I was on - both clear safely even if only one was set.
        if (store.pendingChallenge?.gameId === event.game_id) store.setPendingChallenge(null);
        if (store.incomingGameInvite?.gameId === event.game_id) store.setIncomingGameInvite(null);
        store.setMyGameId(event.game_id);
        store.setGame({
          gameId: event.game_id,
          status: event.status,
          whiteMemberId: event.white_member_id,
          whiteName: event.white_name,
          blackMemberId: event.black_member_id,
          blackName: event.black_name,
          moves: event.moves,
          boardFen: event.board_fen,
          turn: event.turn,
          legalMoves: event.legal_moves,
          inCheck: event.in_check,
          gameOver: event.game_over,
          result: event.result,
          termination: event.termination,
          lastMove: event.last_move,
        });
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
