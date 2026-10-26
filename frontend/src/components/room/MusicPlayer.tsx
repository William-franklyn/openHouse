"use client";

import { useEffect, useRef, useState } from "react";
import { Music, X } from "lucide-react";
import { useRoomStore } from "@/lib/store";
import { api } from "@/lib/api";

export function MusicPlayer({
  token,
  canManage,
  onStop,
}: {
  token: string;
  canManage: boolean;
  onStop: () => void;
}) {
  const music = useRoomStore((s) => s.music);
  const audioRef = useRef<HTMLAudioElement>(null);
  const loadedKeyRef = useRef<string | null>(null);
  const [needsTap, setNeedsTap] = useState(false);

  // Keyed on source+fileId/url+startedAtMs, not just fileId - a reconnect
  // resends the identical snapshot, which must NOT reload/restart playback
  // for a client that's already listening in sync.
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    if (!music) {
      loadedKeyRef.current = null;
      audio.pause();
      audio.removeAttribute("src");
      setNeedsTap(false);
      return;
    }

    const key = `${music.source}:${music.fileId ?? music.url}:${music.startedAtMs}`;
    if (loadedKeyRef.current === key) return;
    loadedKeyRef.current = key;
    setNeedsTap(false);

    let cancelled = false;

    function startFrom(src: string) {
      if (cancelled) return;
      audio!.src = src;
      audio!.addEventListener(
        "loadedmetadata",
        () => {
          if (cancelled) return;
          const offsetSeconds = (Date.now() - music!.startedAtMs) / 1000;
          if (Number.isFinite(audio!.duration) && offsetSeconds >= audio!.duration) {
            // Joined after the track would already be over - nothing to play.
            return;
          }
          audio!.currentTime = Math.max(0, offsetSeconds);
          audio!.play().catch(() => {
            if (!cancelled) setNeedsTap(true);
          });
        },
        { once: true }
      );
    }

    if (music.source === "library") {
      // A permanent public CDN link - no presigned URL to fetch, unlike uploads.
      startFrom(music.url!);
    } else {
      api
        .downloadFile(music.fileId!, token)
        .then((res) => startFrom(res.url))
        .catch(() => {
          // Couldn't get a playable URL - nothing to clean up, just no audio.
        });
    }

    return () => {
      cancelled = true;
    };
  }, [music, token]);

  // Detached <audio> elements don't reliably stop synchronously with
  // unmount in every browser - this is the one line that makes "leaving
  // the room stops my own audio" actually true.
  useEffect(() => {
    return () => {
      audioRef.current?.pause();
    };
  }, []);

  function handleEnded() {
    if (canManage) onStop();
  }

  function retryPlay() {
    audioRef.current
      ?.play()
      .then(() => setNeedsTap(false))
      .catch(() => {});
  }

  return (
    <>
      <audio ref={audioRef} onEnded={handleEnded} />
      {music && (
        <div className="flex items-center gap-3 border-b border-border bg-accent-soft px-4 py-2">
          <Music size={15} className="shrink-0 text-accent" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-[13px] font-medium text-foreground">{music.filename}</p>
            <p className="truncate text-[11px] text-muted">
              Started by {music.startedByName}
              {music.attribution ? ` · ${music.attribution}` : ""}
            </p>
          </div>
          {needsTap && (
            <button
              type="button"
              onClick={retryPlay}
              className="shrink-0 rounded-[var(--radius-sm)] bg-accent px-3 py-1 text-[12px] font-medium text-accent-foreground hover:bg-accent-hover"
            >
              Tap to join the music
            </button>
          )}
          {canManage && (
            <button
              type="button"
              onClick={onStop}
              aria-label="Stop music"
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded text-muted hover:bg-sidebar-hover hover:text-foreground"
            >
              <X size={15} />
            </button>
          )}
        </div>
      )}
    </>
  );
}
