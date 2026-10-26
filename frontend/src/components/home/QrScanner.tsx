"use client";

import { useEffect, useRef, useState } from "react";
import jsQR from "jsqr";
import { Modal } from "@/components/ui/Modal";

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
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
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
        const video = videoRef.current;
        if (!video) return;
        video.srcObject = stream;
        // videoWidth/videoHeight are 0 until a frame has actually decoded -
        // grabbing frames before that gives an empty canvas to scan.
        await new Promise<void>((resolve) => {
          video.onloadedmetadata = () => resolve();
        });
        await video.play();
        if (cancelled) return;

        const canvas = canvasRef.current;
        const ctx = canvas?.getContext("2d", { willReadFrequently: true });

        const tick = () => {
          if (cancelled || !video || !canvas || !ctx) return;
          if (video.readyState === video.HAVE_ENOUGH_DATA) {
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
            const frame = ctx.getImageData(0, 0, canvas.width, canvas.height);
            const result = jsQR(frame.data, frame.width, frame.height);
            if (result) {
              onDetected(result.data);
              return;
            }
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
  }, [open, onDetected]);

  return (
    <Modal open={open} onClose={onClose} title="Scan QR code">
      {error ? (
        <p className="text-sm text-danger">{error}</p>
      ) : (
        <video
          ref={videoRef}
          muted
          playsInline
          className="aspect-square w-full rounded-[var(--radius-md)] bg-black object-cover"
        />
      )}
      <canvas ref={canvasRef} className="hidden" />
    </Modal>
  );
}
