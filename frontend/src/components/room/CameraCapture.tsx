"use client";

import { useEffect, useRef, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";

export function CameraCapture({
  open,
  onClose,
  onSend,
}: {
  open: boolean;
  onClose: () => void;
  onSend: (file: File) => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [capturedUrl, setCapturedUrl] = useState<string | null>(null);
  const capturedBlobRef = useRef<Blob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [videoReady, setVideoReady] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setVideoReady(false);

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
        if (video) {
          video.srcObject = stream;
          // videoWidth/videoHeight are 0 until the browser has decoded at
          // least one frame - capturing before this gives a blank/0x0 image.
          await new Promise<void>((resolve) => {
            video.onloadedmetadata = () => resolve();
          });
          await video.play();
          if (!cancelled) setVideoReady(true);
        }
      } catch {
        setError("Couldn't access the camera.");
      }
    }

    start();
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
  }, [open]);

  function handleClose() {
    if (capturedUrl) URL.revokeObjectURL(capturedUrl);
    setCapturedUrl(null);
    capturedBlobRef.current = null;
    setError(null);
    onClose();
  }

  function capture() {
    const video = videoRef.current;
    if (!video) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0);
    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        capturedBlobRef.current = blob;
        setCapturedUrl(URL.createObjectURL(blob));
      },
      "image/jpeg",
      0.9
    );
  }

  function retake() {
    if (capturedUrl) URL.revokeObjectURL(capturedUrl);
    setCapturedUrl(null);
    capturedBlobRef.current = null;
  }

  function send() {
    if (!capturedBlobRef.current) return;
    const file = new File([capturedBlobRef.current], `photo-${Date.now()}.jpg`, { type: "image/jpeg" });
    handleClose();
    onSend(file);
  }

  return (
    <Modal open={open} onClose={handleClose} title="Take a photo">
      {error ? (
        <p className="text-sm text-danger">{error}</p>
      ) : capturedUrl ? (
        <div className="flex flex-col gap-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={capturedUrl} alt="Captured" className="aspect-square w-full rounded-lg object-cover" />
          <div className="flex gap-2">
            <Button variant="secondary" className="flex-1" onClick={retake}>
              Retake
            </Button>
            <Button className="flex-1" onClick={send}>
              Send
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <video
            ref={videoRef}
            muted
            playsInline
            className="aspect-square w-full rounded-lg bg-black object-cover"
          />
          <Button onClick={capture} disabled={!videoReady}>
            {videoReady ? "📸 Capture" : "Starting camera…"}
          </Button>
        </div>
      )}
    </Modal>
  );
}
