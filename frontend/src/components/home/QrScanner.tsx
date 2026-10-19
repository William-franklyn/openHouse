"use client";

import { useEffect, useRef, useState } from "react";
import { Modal } from "@/components/ui/Modal";

// BarcodeDetector is a native, no-dependency browser API (Chrome/Edge/Android
// Chrome, Safari 17+). Firefox doesn't support it yet - we detect and fall
// back to a plain message rather than shipping a JS decoder for everyone.
declare global {
  interface Window {
    BarcodeDetector?: new (options: { formats: string[] }) => {
      detect: (source: CanvasImageSource) => Promise<{ rawValue: string }[]>;
    };
  }
}

export function QrScanner({
  open,
  onClose,
  onDetected,
}: {
  open: boolean;
  onClose: () => void;
  onDetected: (value: string) => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [error, setError] = useState<string | null>(null);
  const supported = typeof window !== "undefined" && "BarcodeDetector" in window;

  useEffect(() => {
    if (!open || !supported) return;
    let cancelled = false;
    let rafId: number;

    async function start() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "environment" },
        });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }

        const detector = new window.BarcodeDetector!({ formats: ["qr_code"] });
        const tick = async () => {
          if (cancelled || !videoRef.current) return;
          try {
            const codes = await detector.detect(videoRef.current);
            if (codes.length > 0) {
              onDetected(codes[0].rawValue);
              return;
            }
          } catch {
            // transient decode errors are normal mid-scan, keep trying
          }
          rafId = requestAnimationFrame(tick);
        };
        rafId = requestAnimationFrame(tick);
      } catch {
        setError("Couldn't access the camera. You can still type the code in.");
      }
    }

    start();
    return () => {
      cancelled = true;
      if (rafId) cancelAnimationFrame(rafId);
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
  }, [open, supported, onDetected]);

  return (
    <Modal open={open} onClose={onClose} title="Scan QR code">
      {!supported ? (
        <p className="text-sm text-muted">
          QR scanning isn&apos;t supported in this browser. Type the invite code in instead.
        </p>
      ) : error ? (
        <p className="text-sm text-danger">{error}</p>
      ) : (
        <video
          ref={videoRef}
          muted
          playsInline
          className="aspect-square w-full rounded-lg bg-black object-cover"
        />
      )}
    </Modal>
  );
}
