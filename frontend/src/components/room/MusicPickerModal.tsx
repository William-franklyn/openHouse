"use client";

import { ChangeEvent, useEffect, useRef, useState } from "react";
import { Play } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Spinner } from "@/components/ui/Spinner";
import { api } from "@/lib/api";
import { useRoomStore } from "@/lib/store";
import { ApiError, MusicLibraryTrack } from "@/lib/types";

const MUSIC_ACCEPT = ".mp3,.wav,.ogg,.m4a,.webm";

export type MusicPick = { file_id: string } | { library_track_id: string };

export function MusicPickerModal({
  open,
  onClose,
  roomId,
  token,
  onPicked,
}: {
  open: boolean;
  onClose: () => void;
  roomId: string;
  token: string;
  onPicked: (pick: MusicPick) => void;
}) {
  const [uploading, setUploading] = useState(false);
  const [tracks, setTracks] = useState<MusicLibraryTrack[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    api
      .musicLibrary()
      .then((res) => setTracks(res.tracks))
      .catch(() => setTracks([]));
  }, [open]);

  async function handleFilePicked(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;

    setUploading(true);
    try {
      const res = await api.uploadFile(roomId, token, file);
      onPicked({ file_id: res.file_id });
      onClose();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Upload failed.";
      useRoomStore.getState().setError(err instanceof ApiError ? err.code : "upload_failed", message);
    } finally {
      setUploading(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Play music">
      <div className="flex flex-col gap-3">
        <p className="text-[13px] text-muted">
          Everyone in the room will hear it together as background while you chat.
        </p>

        <div className="flex max-h-64 flex-col gap-0.5 overflow-y-auto rounded-[var(--radius-md)] border border-border p-1.5">
          {tracks.length === 0 ? (
            <p className="px-2 py-3 text-center text-[12px] text-muted">Loading library…</p>
          ) : (
            tracks.map((track) => (
              <button
                key={track.id}
                type="button"
                onClick={() => {
                  onPicked({ library_track_id: track.id });
                  onClose();
                }}
                className="flex w-full items-center gap-2.5 rounded-[var(--radius-sm)] px-2.5 py-2 text-left transition-colors hover:bg-surface-muted"
              >
                <Play size={14} className="shrink-0 text-accent" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-medium text-foreground">
                    {track.title}
                  </span>
                  <span className="block truncate text-[11px] text-muted">
                    {track.artist} · {track.license}
                  </span>
                </span>
              </button>
            ))
          )}
        </div>

        <div className="flex items-center gap-3 text-[11px] text-muted">
          <div className="h-px flex-1 bg-border" />
          or bring your own
          <div className="h-px flex-1 bg-border" />
        </div>

        {/* Not display:none - see the identical note in MessageInput.tsx:
            iOS Safari can fail to fire change on a display:none file input
            once the native picker returns. */}
        <input
          ref={fileRef}
          type="file"
          style={{ position: "absolute", width: 1, height: 1, opacity: 0, pointerEvents: "none" }}
          onChange={handleFilePicked}
          accept={MUSIC_ACCEPT}
        />

        <button
          type="button"
          disabled={uploading}
          onClick={() => fileRef.current?.click()}
          className="flex items-center justify-center gap-2 rounded-[var(--radius-md)] border border-dashed border-border px-4 py-4 text-[13px] font-medium text-muted transition-colors hover:border-accent hover:text-accent disabled:opacity-60"
        >
          {uploading ? (
            <>
              <Spinner className="h-4 w-4" />
              Uploading…
            </>
          ) : (
            "Choose an audio file"
          )}
        </button>
      </div>
    </Modal>
  );
}
