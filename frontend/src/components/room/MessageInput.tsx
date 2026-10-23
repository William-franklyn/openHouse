"use client";

import { ChangeEvent, FormEvent, KeyboardEvent, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/types";
import { VoiceRecorder } from "./VoiceRecorder";
import { CameraCapture } from "./CameraCapture";

export function MessageInput({
  roomId,
  channelId,
  token,
  onSend,
}: {
  roomId: string;
  channelId: string;
  token: string;
  onSend: (text: string) => void;
}) {
  const [text, setText] = useState("");
  const [uploading, setUploading] = useState(false);
  const [recording, setRecording] = useState(false);
  const [showCamera, setShowCamera] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed) return;
    onSend(trimmed);
    setText("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  }

  function autoGrow(e: ChangeEvent<HTMLTextAreaElement>) {
    setText(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }

  async function uploadFile(file: File) {
    setUploading(true);
    try {
      await api.uploadFile(roomId, token, file, channelId);
    } catch (err) {
      alert(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  async function handleFilePicked(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) await uploadFile(file);
  }

  if (recording) {
    return (
      <div className="border-t border-border p-3">
        <VoiceRecorder
          onCancel={() => setRecording(false)}
          onSend={(file) => {
            setRecording(false);
            uploadFile(file);
          }}
        />
      </div>
    );
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-end gap-1.5 border-t border-border bg-background p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pl-[max(0.75rem,env(safe-area-inset-left))] pr-[max(0.75rem,env(safe-area-inset-right))]"
    >
      <input
        ref={fileRef}
        type="file"
        className="hidden"
        onChange={handleFilePicked}
        accept=".png,.jpg,.jpeg,.gif,.webp,.pdf,.doc,.docx,.txt,.odt,.zip"
      />

      <button
        type="button"
        disabled={uploading}
        onClick={() => fileRef.current?.click()}
        aria-label="Attach file"
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-lg text-muted hover:bg-surface-muted disabled:opacity-50"
      >
        {uploading ? "…" : "📎"}
      </button>

      <button
        type="button"
        disabled={uploading}
        onClick={() => setShowCamera(true)}
        aria-label="Take a photo"
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-lg text-muted hover:bg-surface-muted disabled:opacity-50"
      >
        📷
      </button>

      <div className="flex flex-1 items-end rounded-3xl border border-border bg-surface px-3.5 py-2">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={autoGrow}
          onKeyDown={handleKeyDown}
          rows={1}
          maxLength={2000}
          placeholder="Message"
          className="max-h-[120px] flex-1 resize-none bg-transparent text-base leading-6 outline-none"
        />
      </div>

      {text.trim() ? (
        <Button type="submit" size="sm" className="shrink-0 rounded-full px-4">
          Send
        </Button>
      ) : (
        <button
          type="button"
          disabled={uploading}
          onClick={() => setRecording(true)}
          aria-label="Record a voice message"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent text-lg text-accent-foreground disabled:opacity-50"
        >
          🎤
        </button>
      )}

      <CameraCapture
        open={showCamera}
        onClose={() => setShowCamera(false)}
        onSend={(file) => uploadFile(file)}
      />
    </form>
  );
}
