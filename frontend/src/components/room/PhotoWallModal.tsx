"use client";

import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Images, Pause, Play, X } from "lucide-react";
import { api } from "@/lib/api";
import { useRoomStore } from "@/lib/store";
import { Spinner } from "@/components/ui/Spinner";

const SLIDESHOW_INTERVAL_MS = 5000;

function PhotoTile({ url, label }: { url: string; label: string }) {
  return (
    <div className="group relative aspect-square overflow-hidden rounded-[var(--radius-md)] bg-surface-muted">
      <img src={url} alt={label} className="h-full w-full object-cover" loading="lazy" />
      <span className="absolute inset-x-0 bottom-0 truncate bg-gradient-to-t from-black/60 to-transparent px-2 py-1.5 text-[11px] text-white opacity-0 transition-opacity group-hover:opacity-100">
        {label}
      </span>
    </div>
  );
}

export function PhotoWallModal({
  open,
  onClose,
  roomId,
  token,
}: {
  open: boolean;
  onClose: () => void;
  roomId: string;
  token: string;
}) {
  const photos = useRoomStore((s) => s.photos);
  const mergePhotos = useRoomStore((s) => s.mergePhotos);
  const [urls, setUrls] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [slideshow, setSlideshow] = useState(false);
  const [playing, setPlaying] = useState(true);
  const [index, setIndex] = useState(0);

  // Seed with the full room-wide history on open - the store's `photos`
  // from here on is kept current by the photo_shared broadcast, but that
  // only covers shares that happen while this session's socket is
  // connected, not everything ever shared in the room.
  useEffect(() => {
    if (!open) return;
    setLoading(true);
    api
      .roomPhotos(roomId, token)
      .then((res) => mergePhotos(res.photos))
      .finally(() => setLoading(false));
  }, [open, roomId, token, mergePhotos]);

  // Resolve a presigned URL for any photo that doesn't have one cached
  // yet - only the newly-added ones, not the whole list every time.
  useEffect(() => {
    if (!open) return;
    const missing = photos.filter((p) => !urls[p.file_id]);
    if (missing.length === 0) return;
    let cancelled = false;
    Promise.all(
      missing.map((p) =>
        api
          .downloadFile(p.file_id, token)
          .then((res) => [p.file_id, res.url] as const)
          .catch(() => null)
      )
    ).then((results) => {
      if (cancelled) return;
      setUrls((prev) => {
        const next = { ...prev };
        for (const r of results) {
          if (r) next[r[0]] = r[1];
        }
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
  }, [photos, open, token, urls]);

  // Keep the slideshow pointer in range as photos arrive/are removed.
  useEffect(() => {
    if (index >= photos.length) setIndex(Math.max(0, photos.length - 1));
  }, [photos.length, index]);

  useEffect(() => {
    if (!open || !slideshow || !playing || photos.length < 2) return;
    const timer = setInterval(() => {
      setIndex((i) => (i + 1) % photos.length);
    }, SLIDESHOW_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [open, slideshow, playing, photos.length]);

  if (!open) return null;

  const current = photos[index];
  const currentUrl = current ? urls[current.file_id] : null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="flex h-[min(90vh,800px)] w-[min(95vw,1100px)] flex-col overflow-hidden rounded-[var(--radius-lg)] border border-border bg-surface shadow-[var(--shadow-lg)]">
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-border px-4">
          <div className="flex items-center gap-2">
            <Images size={17} className="text-accent" />
            <div>
              <h2 className="text-[15px] font-semibold text-foreground">Photo Wall</h2>
              <p className="text-[11px] text-muted">
                {photos.length} photo{photos.length === 1 ? "" : "s"} shared in this room
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {photos.length > 1 && (
              <button
                type="button"
                onClick={() => {
                  setSlideshow((v) => !v);
                  setPlaying(true);
                }}
                className={`rounded-[var(--radius-sm)] px-3 py-1.5 text-[12px] font-medium transition-colors ${
                  slideshow ? "bg-accent-soft text-accent" : "text-muted hover:bg-surface-muted"
                }`}
              >
                {slideshow ? "Grid view" : "Slideshow"}
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="flex h-8 w-8 items-center justify-center rounded-full text-muted hover:bg-surface-muted hover:text-foreground"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        <div className="relative flex-1 overflow-hidden">
          {loading && photos.length === 0 ? (
            <div className="flex h-full items-center justify-center">
              <Spinner className="h-6 w-6 text-accent" />
            </div>
          ) : photos.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-muted">
              <Images size={28} className="opacity-50" />
              <p className="text-sm">No photos shared yet. Attach an image in chat to kick it off.</p>
            </div>
          ) : slideshow ? (
            <div className="flex h-full flex-col">
              <div className="relative flex-1 bg-black">
                {currentUrl ? (
                  <img
                    key={current.file_id}
                    src={currentUrl}
                    alt={current.filename}
                    className="animate-fade-in h-full w-full object-contain"
                  />
                ) : (
                  <div className="flex h-full items-center justify-center">
                    <Spinner className="h-6 w-6 text-white" />
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => setIndex((i) => (i - 1 + photos.length) % photos.length)}
                  aria-label="Previous photo"
                  className="absolute left-2 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-black/40 text-white hover:bg-black/60"
                >
                  <ChevronLeft size={18} />
                </button>
                <button
                  type="button"
                  onClick={() => setIndex((i) => (i + 1) % photos.length)}
                  aria-label="Next photo"
                  className="absolute right-2 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-black/40 text-white hover:bg-black/60"
                >
                  <ChevronRight size={18} />
                </button>
              </div>
              <div className="flex shrink-0 items-center justify-center gap-3 border-t border-border py-2.5">
                <button
                  type="button"
                  onClick={() => setPlaying((v) => !v)}
                  aria-label={playing ? "Pause slideshow" : "Play slideshow"}
                  className="flex h-8 w-8 items-center justify-center rounded-full text-muted hover:bg-surface-muted hover:text-foreground"
                >
                  {playing ? <Pause size={15} /> : <Play size={15} />}
                </button>
                <span className="text-[12px] text-muted">
                  {current?.member_name ? `Shared by ${current.member_name}` : ""} · {index + 1}/{photos.length}
                </span>
              </div>
            </div>
          ) : (
            <div className="h-full overflow-y-auto p-4">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                {photos
                  .slice()
                  .reverse()
                  .map((p) =>
                    urls[p.file_id] ? (
                      <PhotoTile
                        key={p.file_id}
                        url={urls[p.file_id]}
                        label={p.member_name ? `${p.member_name}` : p.filename}
                      />
                    ) : (
                      <div
                        key={p.file_id}
                        className="flex aspect-square items-center justify-center rounded-[var(--radius-md)] bg-surface-muted"
                      >
                        <Spinner className="h-5 w-5 text-muted" />
                      </div>
                    )
                  )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
