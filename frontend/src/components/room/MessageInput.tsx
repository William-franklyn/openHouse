"use client";

import { ChangeEvent, FormEvent, KeyboardEvent, useRef, useState } from "react";
import { Paperclip, Camera, Mic, Send } from "lucide-react";
import { Tooltip } from "@/components/ui/Tooltip";
import { api } from "@/lib/api";
import { useRoomStore } from "@/lib/store";
import { ApiError } from "@/lib/types";
import { VoiceRecorder } from "./VoiceRecorder";
import { CameraCapture } from "./CameraCapture";

const iconButtonClass =
  "flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-sm)] text-muted transition-colors hover:bg-surface-muted hover:text-foreground disabled:opacity-40 disabled:pointer-events-none";

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
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }

  async function uploadFile(file: File) {
    setUploading(true);
    try {
      await api.uploadFile(roomId, token, file, channelId);
    } catch (err) {
      // Not window.alert(): iOS silently swallows alert() for apps
      // installed to the home screen (standalone display mode), which
      // would make a real failure look like nothing happened at all.
      const message = err instanceof ApiError ? err.message : "Upload failed.";
      useRoomStore.getState().setError(err instanceof ApiError ? err.code : "upload_failed", message);
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
      <div className="border-t border-border bg-surface p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
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
      className="border-t border-border bg-surface px-3 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pl-[max(0.75rem,env(safe-area-inset-left))] pr-[max(0.75rem,env(safe-area-inset-right))] sm:px-4"
    >
      {/* Not display:none (className="hidden") - iOS Safari has a
          long-standing bug where a file <input>'s change event fires
          unreliably once the native picker returns if the input isn't
          actually in the render tree. This keeps it there but invisible. */}
      <input
        ref={fileRef}
        type="file"
        style={{ position: "absolute", width: 1, height: 1, opacity: 0, pointerEvents: "none" }}
        onChange={handleFilePicked}
        accept=".png,.jpg,.jpeg,.gif,.webp,.pdf,.doc,.docx,.txt,.odt,.zip"
      />

      <div className="flex items-end gap-1 rounded-[var(--radius-lg)] border border-border bg-background px-1.5 py-1.5 transition-colors focus-within:border-accent">
        <Tooltip label="Attach file">
          <button
            type="button"
            disabled={uploading}
            onClick={() => fileRef.current?.click()}
            aria-label="Attach file"
            className={iconButtonClass}
          >
            <Paperclip size={18} />
          </button>
        </Tooltip>

        <Tooltip label="Take a photo">
          <button
            type="button"
            disabled={uploading}
            onClick={() => setShowCamera(true)}
            aria-label="Take a photo"
            className={iconButtonClass}
          >
            <Camera size={18} />
          </button>
        </Tooltip>

        <textarea
          ref={textareaRef}
          value={text}
          onChange={autoGrow}
          onKeyDown={handleKeyDown}
          rows={1}
          maxLength={2000}
          placeholder="Message"
          aria-label="Message"
          // text-[16px] (not 14px): below 16px, iOS/Android browsers
          // auto-zoom the whole page on focus to make the text legible -
          // that's the "it zooms in" jump. outline-none! (important):
          // the global :focus-visible ring in globals.css otherwise wins
          // the cascade and overrides the plain outline-none below it.
          className="min-h-9 max-h-40 flex-1 resize-none bg-transparent px-1 py-1.5 text-[16px] leading-relaxed text-foreground outline-none! placeholder:text-muted"
        />

        {text.trim() ? (
          <Tooltip label="Send">
            <button
              type="submit"
              aria-label="Send message"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-sm)] bg-accent text-accent-foreground transition-colors hover:bg-accent-hover"
            >
              <Send size={15} />
            </button>
          </Tooltip>
        ) : (
          <Tooltip label="Record a voice message">
            <button
              type="button"
              disabled={uploading}
              onClick={() => setRecording(true)}
              aria-label="Record a voice message"
              className={iconButtonClass}
            >
              <Mic size={18} />
            </button>
          </Tooltip>
        )}
      </div>

      <CameraCapture
        open={showCamera}
        onClose={() => setShowCamera(false)}
        onSend={(file) => uploadFile(file)}
      />
    </form>
  );
}
