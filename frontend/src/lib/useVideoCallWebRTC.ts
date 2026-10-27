"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRoomStore } from "./store";
import { CallSignalEvent } from "./types";

const ICE_SERVERS: RTCIceServer[] = [{ urls: "stun:stun.l.google.com:19302" }];
const EMPTY_PRESENCE: string[] = [];

type SendFn = (type: string, data?: Record<string, unknown>) => void;

interface Peer {
  connection: RTCPeerConnection;
  pendingCandidates: RTCIceCandidateInit[];
}

/** Mesh WebRTC: every participant connects directly to every other
 * participant (no media server). For any given pair, whoever has the
 * lexicographically smaller member_id is the one who creates the offer -
 * a simple, race-free rule so both sides can independently agree on who
 * initiates without any central coordinator or "who joined first" state. */
export function useVideoCallWebRTC(callId: string, myMemberId: string, send: SendFn) {
  const [joined, setJoined] = useState(false);
  const [localStream, setLocalStream] = useState<MediaStream | null>(null);
  const [remoteStreams, setRemoteStreams] = useState<Record<string, MediaStream>>({});
  const [muted, setMuted] = useState(false);
  const [cameraOff, setCameraOff] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const peersRef = useRef<Map<string, Peer>>(new Map());
  const localStreamRef = useRef<MediaStream | null>(null);
  const joinedRef = useRef(false);

  const callPresence = useRoomStore((s) => s.callPresenceByCallId[callId] ?? EMPTY_PRESENCE);
  const callSignalQueue = useRoomStore((s) => s.callSignalQueue);

  const closePeer = useCallback((peerId: string) => {
    const peer = peersRef.current.get(peerId);
    if (!peer) return;
    peer.connection.close();
    peersRef.current.delete(peerId);
    setRemoteStreams((prev) => {
      if (!(peerId in prev)) return prev;
      const next = { ...prev };
      delete next[peerId];
      return next;
    });
  }, []);

  const getOrCreatePeer = useCallback(
    (peerId: string): Peer => {
      const existing = peersRef.current.get(peerId);
      if (existing) return existing;

      const connection = new RTCPeerConnection({ iceServers: ICE_SERVERS });
      localStreamRef.current?.getTracks().forEach((track) => {
        connection.addTrack(track, localStreamRef.current!);
      });

      connection.onicecandidate = (e) => {
        // A null candidate just marks "ICE gathering finished" - trickle
        // ICE doesn't need that forwarded, only real candidates do.
        if (e.candidate) {
          send("call_ice_candidate", { to_member_id: peerId, candidate: e.candidate.toJSON() });
        }
      };

      connection.ontrack = (e) => {
        setRemoteStreams((prev) => ({ ...prev, [peerId]: e.streams[0] }));
      };

      connection.onconnectionstatechange = () => {
        if (connection.connectionState === "failed" || connection.connectionState === "closed") {
          closePeer(peerId);
        }
      };

      const peer: Peer = { connection, pendingCandidates: [] };
      peersRef.current.set(peerId, peer);
      return peer;
    },
    [send, closePeer]
  );

  const initiateTo = useCallback(
    async (peerId: string) => {
      const peer = getOrCreatePeer(peerId);
      const offer = await peer.connection.createOffer();
      await peer.connection.setLocalDescription(offer);
      send("call_offer", { to_member_id: peerId, sdp: offer });
    },
    [getOrCreatePeer, send]
  );

  // Reacts to who's in the call: connect to newcomers (per the
  // smaller-id-initiates rule), tear down connections for anyone who left.
  useEffect(() => {
    if (!joined) return;
    const others = callPresence.filter((id) => id !== myMemberId);

    for (const peerId of others) {
      if (peersRef.current.has(peerId)) continue;
      if (myMemberId < peerId) {
        initiateTo(peerId).catch(() => setError("Couldn't connect to a participant."));
      }
      // else: wait for their offer - created reactively below.
    }

    const current = new Set(others);
    for (const peerId of Array.from(peersRef.current.keys())) {
      if (!current.has(peerId)) closePeer(peerId);
    }
  }, [callPresence, joined, myMemberId, initiateTo, closePeer]);

  // Drains the signal queue in arrival order, then clears it - see the
  // store's comment on callSignalQueue for why this is a queue and not
  // an overwritable "last value".
  useEffect(() => {
    if (callSignalQueue.length === 0) return;

    async function process(event: CallSignalEvent) {
      const peerId = event.from_member_id;

      if (event.type === "call_offer") {
        const peer = getOrCreatePeer(peerId);
        await peer.connection.setRemoteDescription(event.sdp);
        for (const candidate of peer.pendingCandidates.splice(0)) {
          await peer.connection.addIceCandidate(candidate);
        }
        const answer = await peer.connection.createAnswer();
        await peer.connection.setLocalDescription(answer);
        send("call_answer", { to_member_id: peerId, sdp: answer });
        return;
      }

      const peer = peersRef.current.get(peerId);
      if (!peer) return; // stale signal for a connection we've already torn down

      if (event.type === "call_answer") {
        await peer.connection.setRemoteDescription(event.sdp);
        for (const candidate of peer.pendingCandidates.splice(0)) {
          await peer.connection.addIceCandidate(candidate);
        }
      } else if (event.type === "ice_candidate") {
        if (peer.connection.remoteDescription) {
          await peer.connection.addIceCandidate(event.candidate);
        } else {
          peer.pendingCandidates.push(event.candidate);
        }
      }
    }

    const queued = callSignalQueue;
    useRoomStore.getState().clearCallSignals();
    (async () => {
      for (const event of queued) {
        try {
          await process(event);
        } catch {
          setError("A connection to a participant dropped.");
        }
      }
    })();
  }, [callSignalQueue, getOrCreatePeer, send]);

  const join = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      localStreamRef.current = stream;
      setLocalStream(stream);
      joinedRef.current = true;
      setJoined(true);
      send("join_call", { call_id: callId });
    } catch {
      setError("Couldn't access your camera/microphone. Check your browser permissions.");
    }
  }, [send, callId]);

  const leave = useCallback(() => {
    if (!joinedRef.current) return;
    joinedRef.current = false;
    setJoined(false);
    send("leave_call", { call_id: callId });
    for (const peerId of Array.from(peersRef.current.keys())) closePeer(peerId);
    localStreamRef.current?.getTracks().forEach((t) => t.stop());
    localStreamRef.current = null;
    setLocalStream(null);
    setRemoteStreams({});
  }, [send, closePeer, callId]);

  const toggleMute = useCallback(() => {
    const stream = localStreamRef.current;
    if (!stream) return;
    const next = !muted;
    stream.getAudioTracks().forEach((t) => (t.enabled = !next));
    setMuted(next);
  }, [muted]);

  const toggleCamera = useCallback(() => {
    const stream = localStreamRef.current;
    if (!stream) return;
    const next = !cameraOff;
    stream.getVideoTracks().forEach((t) => (t.enabled = !next));
    setCameraOff(next);
  }, [cameraOff]);

  // Closing the modal/tab should hang up, same reasoning as MusicPlayer's
  // pause-on-unmount - a dangling open call is worse than a silently
  // missed leave_call broadcast.
  useEffect(() => {
    return () => leave();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [callId]);

  return { joined, localStream, remoteStreams, muted, cameraOff, error, join, leave, toggleMute, toggleCamera };
}
