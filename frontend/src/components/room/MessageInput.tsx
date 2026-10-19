"use client";

import { ChangeEvent, FormEvent, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/types";

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
  const fileRef = useRef<HTMLInputElement>(null);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed) return;
    onSend(trimmed);
    setText("");
  }

  async function handleFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      await api.uploadFile(roomId, token, file, channelId);
    } catch (err) {
      alert(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-end gap-2 border-t border-border p-3">
      <input
        ref={fileRef}
        type="file"
        className="hidden"
        onChange={handleFile}
        accept=".png,.jpg,.jpeg,.gif,.webp,.pdf,.doc,.docx,.txt,.odt,.zip"
      />
      <Button
        type="button"
        variant="secondary"
        size="sm"
        disabled={uploading}
        onClick={() => fileRef.current?.click()}
      >
        {uploading ? "…" : "📎"}
      </Button>
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        maxLength={2000}
        placeholder="Message"
        className="flex-1 rounded-lg border border-border bg-surface px-3.5 py-2.5 text-base focus:outline-2 focus:outline-accent"
      />
      <Button type="submit" size="sm" disabled={!text.trim()}>
        Send
      </Button>
    </form>
  );
}
