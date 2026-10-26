"use client";

import { useEffect, useRef } from "react";
import { Mic, MicOff, Video, VideoOff, PhoneOff, X } from "lucide-react";
import { useVideoCallWebRTC } from "@/lib/useVideoCallWebRTC";
import { Button } from "@/components/ui/Button";

function VideoTile({
  stream,
  label,
  muted,
}: {
  stream: MediaStream;
  label: string;
  muted?: boolean;
}) {
  const ref = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (ref.current) ref.current.srcObject = stream;
  }, [stream]);

  return (
    <div className="relative aspect-video overflow-hidden rounded-[var(--radius-md)] bg-black">
      <video ref={ref} autoPlay playsInline muted={muted} className="h-full w-full object-cover" />
      <span className="absolute bottom-1.5 left-2 rounded bg-black/50 px-1.5 py-0.5 text-[11px] text-white">
        {label}
      </span>
    </div>
  );
}

export function WebRTCCallModal({
  open,
  onClose,
  roomId,
  myMemberId,
  myName,
  send,
}: {
  open: boolean;
  onClose: () => void;
  roomId: string;
  myMemberId: string;
  myName: string;
  send: (type: string, data?: Record<string, unknown>) => void;
}) {
  const { joined, localStream, remoteStreams, muted, cameraOff, error, join, leave, toggleMute, toggleCamera } =
    useVideoCallWebRTC(roomId, myMemberId, send);

  if (!open) return null;

  const remoteEntries = Object.entries(remoteStreams);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="flex h-[min(85vh,700px)] w-full max-w-4xl flex-col overflow-hidden rounded-[var(--radius-lg)] border border-border bg-surface shadow-[var(--shadow-lg)]">
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-border px-4">
          <div>
            <h2 className="text-[15px] font-semibold text-foreground">Video call (WebRTC)</h2>
            <p className="text-[11px] text-muted">Self-hosted peer-to-peer - best for small groups</p>
          </div>
          <button
            type="button"
            onClick={() => {
              leave();
              onClose();
            }}
            aria-label="Close"
            className="flex h-8 w-8 items-center justify-center rounded-full text-muted hover:bg-surface-muted hover:text-foreground"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {error && <p className="mb-3 text-[13px] text-danger">{error}</p>}

          {!joined ? (
            <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
              <p className="text-sm text-muted">
                {remoteEntries.length > 0
                  ? "There's already a call in progress."
                  : "Nobody's in this call yet."}
              </p>
              <Button onClick={join}>Join call</Button>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {localStream && <VideoTile stream={localStream} label={`${myName} (you)`} muted />}
              {remoteEntries.map(([memberId, stream]) => (
                <VideoTile key={memberId} stream={stream} label="Participant" />
              ))}
            </div>
          )}
        </div>

        {joined && (
          <div className="flex h-16 shrink-0 items-center justify-center gap-3 border-t border-border">
            <Button variant="secondary" size="icon" onClick={toggleMute} aria-label={muted ? "Unmute" : "Mute"}>
              {muted ? <MicOff size={16} /> : <Mic size={16} />}
            </Button>
            <Button
              variant="secondary"
              size="icon"
              onClick={toggleCamera}
              aria-label={cameraOff ? "Turn camera on" : "Turn camera off"}
            >
              {cameraOff ? <VideoOff size={16} /> : <Video size={16} />}
            </Button>
            <Button variant="danger" size="icon" onClick={leave} aria-label="Leave call">
              <PhoneOff size={16} />
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
