"use client";

import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/Button";

function formatElapsed(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

/** Extension matching MediaRecorder's chosen mimeType, so the backend's
 * extension allowlist and the player's format sniffing both work. */
function extensionFor(mimeType: string): string {
  if (mimeType.includes("mp4")) return "m4a";
  if (mimeType.includes("ogg")) return "ogg";
  if (mimeType.includes("wav")) return "wav";
  return "webm";
}

export function VoiceRecorder({
  onCancel,
  onSend,
}: {
  onCancel: () => void;
  onSend: (file: File) => void;
}) {
  const [elapsedMs, setElapsedMs] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const startRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setInterval>;

    async function start() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        const recorder = new MediaRecorder(stream);
        recorderRef.current = recorder;
        recorder.ondataavailable = (e) => {
          if (e.data.size > 0) chunksRef.current.push(e.data);
        };
        recorder.start();
        startRef.current = Date.now();
        timer = setInterval(() => setElapsedMs(Date.now() - startRef.current), 200);
      } catch {
        setError("Couldn't access the microphone.");
      }
    }

    start();
    return () => {
      cancelled = true;
      clearInterval(timer);
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  function stopAndSend() {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === "inactive") return;
    recorder.onstop = () => {
      const mimeType = recorder.mimeType || "audio/webm";
      const blob = new Blob(chunksRef.current, { type: mimeType });
      const file = new File([blob], `voice-message.${extensionFor(mimeType)}`, { type: mimeType });
      streamRef.current?.getTracks().forEach((t) => t.stop());
      onSend(file);
    };
    recorder.stop();
  }

  function cancel() {
    recorderRef.current?.stop();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    onCancel();
  }

  if (error) {
    return (
      <div className="flex items-center justify-between gap-2 rounded-[var(--radius-lg)] bg-danger-soft px-3.5 py-2.5 text-sm text-danger">
        {error}
        <button onClick={onCancel} className="text-[13px] font-medium underline underline-offset-2">
          Close
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3 rounded-[var(--radius-lg)] border border-border bg-background px-4 py-2.5">
      <span className="h-2.5 w-2.5 animate-recording-pulse rounded-full bg-danger" />
      <span className="flex-1 font-mono text-sm tabular-nums text-foreground">{formatElapsed(elapsedMs)}</span>
      <button
        type="button"
        onClick={cancel}
        aria-label="Cancel recording"
        className="flex h-7 w-7 items-center justify-center rounded-full text-muted hover:bg-surface-muted hover:text-danger"
      >
        <X size={15} />
      </button>
      <Button type="button" size="sm" onClick={stopAndSend}>
        Send
      </Button>
    </div>
  );
}
