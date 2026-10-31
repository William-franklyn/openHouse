"use client";

import { ChangeEvent, useEffect, useRef, useState } from "react";
import { ChevronDown, ListMusic, Music, Volume1, Volume2, VolumeX, X } from "lucide-react";
import { useRoomStore } from "@/lib/store";
import { api } from "@/lib/api";

const VOLUME_STORAGE_KEY = "openhouse-music-volume";
const REQUEST_NOTICE_TIMEOUT_MS = 10_000;

function loadSavedVolume(): number {
  if (typeof window === "undefined") return 1;
  const saved = window.localStorage.getItem(VOLUME_STORAGE_KEY);
  const parsed = saved !== null ? Number(saved) : NaN;
  return Number.isFinite(parsed) ? Math.min(1, Math.max(0, parsed)) : 1;
}

export function MusicPlayer({
  token,
  onStop,
  onTrackEnded,
  onCancelQueued,
}: {
  token: string;
  onStop: () => void;
  onTrackEnded: (trackId: string) => void;
  onCancelQueued: (trackId: string) => void;
}) {
  const music = useRoomStore((s) => s.music);
  const musicQueue = useRoomStore((s) => s.musicQueue);
  const musicRequestNotice = useRoomStore((s) => s.musicRequestNotice);
  const myMemberId = useRoomStore((s) => s.myMemberId);
  const myRole = useRoomStore((s) => s.myRole);
  const audioRef = useRef<HTMLAudioElement>(null);
  const loadedKeyRef = useRef<string | null>(null);
  const [needsTap, setNeedsTap] = useState(false);
  const [volume, setVolume] = useState(loadSavedVolume);
  const [muted, setMuted] = useState(false);
  const [queueOpen, setQueueOpen] = useState(false);

  const canStop = !!music && (music.startedByMemberId === myMemberId || myRole === "owner" || myRole === "mod");

  // The person whose track is currently playing is the only one who ever
  // gets a music_requested event (it's a targeted send, not a broadcast),
  // so there's no permission check needed here - just auto-dismiss it so
  // an ignored request doesn't sit there forever.
  useEffect(() => {
    if (!musicRequestNotice) return;
    const timer = window.setTimeout(() => {
      useRoomStore.getState().setMusicRequestNotice(null);
    }, REQUEST_NOTICE_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, [musicRequestNotice]);

  // Applies on every volume/mute change, and also lands on mount before
  // the track-loading effect below ever calls .play() - setting it here
  // rather than once is what makes the slider actually take effect.
  useEffect(() => {
    if (audioRef.current) audioRef.current.volume = muted ? 0 : volume;
  }, [volume, muted]);

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
    // Not a manual stop - every listener's own <audio> fires this near
    // simultaneously, so this just reports "it finished"; the server
    // dedupes by track_id and only the first report actually advances.
    if (music) onTrackEnded(music.id);
  }

  function retryPlay() {
    audioRef.current
      ?.play()
      .then(() => setNeedsTap(false))
      .catch(() => {});
  }

  function handleVolumeChange(e: ChangeEvent<HTMLInputElement>) {
    const next = Number(e.target.value);
    setVolume(next);
    setMuted(false);
    window.localStorage.setItem(VOLUME_STORAGE_KEY, String(next));
  }

  const effectiveVolume = muted ? 0 : volume;
  const VolumeIcon = effectiveVolume === 0 ? VolumeX : effectiveVolume < 0.5 ? Volume1 : Volume2;

  return (
    <>
      <audio ref={audioRef} onEnded={handleEnded} />

      {musicRequestNotice && (
        <div className="flex items-center gap-2 border-b border-border bg-amber-500/10 px-4 py-1.5 text-[12px] text-foreground">
          <Music size={13} className="shrink-0 text-amber-500" />
          <span className="min-w-0 flex-1 truncate">
            <strong className="font-semibold">{musicRequestNotice.requestedByName}</strong> wants to play{" "}
            <span className="italic">{musicRequestNotice.filename}</span> next.
          </span>
          <button
            type="button"
            onClick={() => {
              onStop();
              useRoomStore.getState().setMusicRequestNotice(null);
            }}
            className="shrink-0 rounded-[var(--radius-sm)] bg-amber-500 px-2.5 py-1 text-[11px] font-medium text-white hover:bg-amber-600"
          >
            Let them play
          </button>
          <button
            type="button"
            onClick={() => useRoomStore.getState().setMusicRequestNotice(null)}
            aria-label="Dismiss"
            className="shrink-0 text-muted hover:text-foreground"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {music && (
        <div className="flex flex-col border-b border-border bg-accent-soft">
          <div className="flex items-center gap-3 px-4 py-2">
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
            {musicQueue.length > 0 && (
              <button
                type="button"
                onClick={() => setQueueOpen((v) => !v)}
                aria-expanded={queueOpen}
                className="flex shrink-0 items-center gap-1 rounded-[var(--radius-sm)] px-2 py-1 text-[11px] font-medium text-muted hover:bg-sidebar-hover hover:text-foreground"
              >
                <ListMusic size={13} />
                {musicQueue.length} queued
                <ChevronDown size={12} className={queueOpen ? "rotate-180" : ""} />
              </button>
            )}
            <div className="flex shrink-0 items-center gap-1.5">
              <button
                type="button"
                onClick={() => setMuted((v) => !v)}
                aria-label={muted ? "Unmute" : "Mute"}
                className="flex h-6 w-6 items-center justify-center text-muted hover:text-foreground"
              >
                <VolumeIcon size={15} />
              </button>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={effectiveVolume}
                onChange={handleVolumeChange}
                aria-label="Music volume"
                className="h-1 w-16 accent-accent sm:w-20"
              />
            </div>
            {canStop && (
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

          {queueOpen && musicQueue.length > 0 && (
            <div className="flex flex-col gap-0.5 border-t border-border/60 px-4 py-2">
              {musicQueue.map((t, i) => {
                const canCancel = t.requestedByMemberId === myMemberId || myRole === "owner" || myRole === "mod";
                return (
                  <div key={t.id} className="flex items-center gap-2 py-0.5 text-[12px]">
                    <span className="w-4 shrink-0 text-muted">{i + 1}.</span>
                    <span className="min-w-0 flex-1 truncate text-foreground">{t.filename}</span>
                    <span className="shrink-0 text-muted">{t.requestedByName}</span>
                    {canCancel && (
                      <button
                        type="button"
                        onClick={() => onCancelQueued(t.id)}
                        aria-label={`Remove ${t.filename} from queue`}
                        className="flex h-5 w-5 shrink-0 items-center justify-center rounded text-muted hover:bg-sidebar-hover hover:text-foreground"
                      >
                        <X size={12} />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </>
  );
}
