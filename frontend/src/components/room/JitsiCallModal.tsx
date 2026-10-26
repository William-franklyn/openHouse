"use client";

import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";

const JITSI_SCRIPT_SRC = "https://meet.jit.si/external_api.js";

// Jitsi's External API is loaded from their script tag at runtime, not a
// package - there's no first-party type package worth hand-rolling full
// types for just this one embed.
type JitsiApi = {
  dispose: () => void;
  addListener: (event: string, handler: (...args: unknown[]) => void) => void;
};

declare global {
  interface Window {
    JitsiMeetExternalAPI?: new (domain: string, options: Record<string, unknown>) => JitsiApi;
  }
}

function loadJitsiScript(): Promise<void> {
  if (window.JitsiMeetExternalAPI) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${JITSI_SCRIPT_SRC}"]`);
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("Failed to load Jitsi.")));
      return;
    }
    const script = document.createElement("script");
    script.src = JITSI_SCRIPT_SRC;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Failed to load Jitsi."));
    document.head.appendChild(script);
  });
}

export function JitsiCallModal({
  open,
  onClose,
  videoRoomToken,
  myName,
  send,
}: {
  open: boolean;
  onClose: () => void;
  videoRoomToken: string;
  myName: string;
  send: (type: string, data?: Record<string, unknown>) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const apiRef = useRef<JitsiApi | null>(null);
  const joinedRef = useRef(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;

    loadJitsiScript()
      .then(() => {
        if (cancelled || !containerRef.current || !window.JitsiMeetExternalAPI) return;

        const api = new window.JitsiMeetExternalAPI("meet.jit.si", {
          roomName: `openhouse-${videoRoomToken}`,
          parentNode: containerRef.current,
          width: "100%",
          height: "100%",
          userInfo: { displayName: myName },
          // disableDeepLinking: without it, mobile browsers get Jitsi's own
          // "Join in app / download from the App Store / join in browser"
          // interstitial before reaching the call - defeats the point of
          // embedding it directly in the room.
          configOverwrite: { prejoinPageEnabled: false, disableDeepLinking: true },
          interfaceConfigOverwrite: { SHOW_JITSI_WATERMARK: false, SHOW_WATERMARK_FOR_GUESTS: false },
        });
        apiRef.current = api;

        api.addListener("videoConferenceJoined", () => {
          joinedRef.current = true;
          send("join_call", { mode: "jitsi" });
        });
        api.addListener("videoConferenceLeft", () => {
          if (joinedRef.current) {
            joinedRef.current = false;
            send("leave_call", { mode: "jitsi" });
          }
        });
        api.addListener("readyToClose", () => {
          onClose();
        });
      })
      .catch(() => {
        if (!cancelled) setError("Couldn't load Jitsi Meet. Check your connection and try again.");
      });

    return () => {
      cancelled = true;
      if (apiRef.current) {
        if (joinedRef.current) {
          joinedRef.current = false;
          send("leave_call", { mode: "jitsi" });
        }
        apiRef.current.dispose();
        apiRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, videoRoomToken]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="flex h-[min(90vh,800px)] w-full max-w-5xl flex-col overflow-hidden rounded-[var(--radius-lg)] border border-border bg-surface shadow-[var(--shadow-lg)]">
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-border px-4">
          <div>
            <h2 className="text-[15px] font-semibold text-foreground">Video call (Jitsi Meet)</h2>
            <p className="text-[11px] text-muted">Hosted on meet.jit.si - handles larger calls reliably</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="flex h-8 w-8 items-center justify-center rounded-full text-muted hover:bg-surface-muted hover:text-foreground"
          >
            <X size={16} />
          </button>
        </div>

        <div className="relative flex-1">
          {error ? (
            <div className="flex h-full items-center justify-center p-4 text-center text-[13px] text-danger">
              {error}
            </div>
          ) : (
            <div ref={containerRef} className="h-full w-full" />
          )}
        </div>
      </div>
    </div>
  );
}
