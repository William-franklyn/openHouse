"use client";

import { useEffect, useState } from "react";
import { Avatar } from "@/components/ui/Avatar";
import { api } from "@/lib/api";
import { DownloadResponse, MemberRole, MessageOut } from "@/lib/types";

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const AUDIO_EXT = /\.(webm|mp3|wav|ogg|m4a)$/i;
const IMAGE_EXT = /\.(png|jpe?g|gif|webp)$/i;

function FileMessage({ msg, token, isMine }: { msg: MessageOut; token: string; isMine: boolean }) {
  const [info, setInfo] = useState<DownloadResponse | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!msg.file_id) return;
    api
      .downloadFile(msg.file_id, token)
      .then(setInfo)
      .catch(() => setError(true));
  }, [msg.file_id, token]);

  if (error) {
    return <p className="text-sm text-danger">Couldn&apos;t load this file.</p>;
  }
  if (!info) {
    return (
      <div className="flex items-center gap-2 text-sm opacity-70">
        <span className="h-3 w-3 animate-pulse rounded-full bg-current" />
        Loading…
      </div>
    );
  }

  if (AUDIO_EXT.test(info.filename)) {
    return (
      <div className="flex flex-col gap-1">
        <audio controls src={info.url} className="h-10 w-56 max-w-full" />
        <span className={`text-[11px] ${isMine ? "text-accent-foreground/70" : "text-muted"}`}>
          Voice message · {formatSize(info.size)}
        </span>
      </div>
    );
  }

  if (IMAGE_EXT.test(info.filename)) {
    return (
      <a href={info.url} target="_blank" rel="noreferrer" className="block overflow-hidden rounded-xl">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={info.url} alt={info.filename} className="max-h-72 max-w-full rounded-xl object-cover" />
      </a>
    );
  }

  return (
    <a
      href={info.url}
      download={info.filename}
      target="_blank"
      rel="noreferrer"
      className={`inline-flex max-w-xs items-center gap-2 rounded-xl border px-3 py-2 ${
        isMine ? "border-white/20 bg-white/10" : "border-border bg-surface-muted"
      }`}
    >
      <span className="text-lg">📄</span>
      <span className="flex flex-col overflow-hidden">
        <span className="truncate text-sm font-medium">{info.filename}</span>
        <span className={`text-xs ${isMine ? "text-accent-foreground/70" : "text-muted"}`}>
          {formatSize(info.size)}
        </span>
      </span>
    </a>
  );
}

export function MessageItem({
  msg,
  token,
  myRole,
  myMemberId,
  showHeader,
  isPinned,
  onPin,
  onUnpin,
  onDelete,
  onReport,
}: {
  msg: MessageOut;
  token: string;
  myRole: MemberRole | null;
  myMemberId: string | null;
  showHeader: boolean;
  isPinned: boolean;
  onPin: (messageId: string) => void;
  onUnpin: (messageId: string) => void;
  onDelete: (messageId: string) => void;
  onReport: (messageId: string) => void;
}) {
  if (msg.kind === "system") {
    return (
      <div className="flex justify-center py-2">
        <span className="rounded-full bg-surface-muted px-3 py-1 text-xs text-muted">{msg.text}</span>
      </div>
    );
  }

  const isMine = msg.member_id === myMemberId;
  const isAdmin = myRole === "owner" || myRole === "mod";
  const canDelete = isMine || isAdmin;
  const canPin = isAdmin;
  const name = msg.from_name ?? "Someone";

  return (
    <div
      className={`group flex items-end gap-2 px-1 ${isMine ? "flex-row-reverse" : ""} ${showHeader ? "mt-3" : "mt-0.5"}`}
    >
      <div className="w-7 shrink-0">
        {showHeader && !isMine && <Avatar name={name} seed={msg.member_id ?? name} size="sm" />}
      </div>

      <div className={`flex max-w-[75%] flex-col gap-0.5 ${isMine ? "items-end" : "items-start"}`}>
        {showHeader && !isMine && <span className="px-1 text-xs font-medium text-muted">{name}</span>}

        <div className="flex items-center gap-1.5">
          {isMine && (
            <span className="hidden gap-2 text-[11px] text-muted group-hover:flex">
              {canDelete && (
                <button onClick={() => onDelete(msg.id)} className="hover:text-danger">
                  Delete
                </button>
              )}
            </span>
          )}

          <div
            className={`rounded-2xl px-3.5 py-2 ${
              isMine
                ? "rounded-br-md bg-accent text-accent-foreground"
                : "rounded-bl-md border border-border bg-surface"
            }`}
          >
            {msg.kind === "file" ? (
              <FileMessage msg={msg} token={token} isMine={isMine} />
            ) : (
              <p className="whitespace-pre-wrap break-words text-sm">{msg.text}</p>
            )}
          </div>

          {!isMine && (
            <span className="hidden gap-2 text-[11px] text-muted group-hover:flex">
              {canPin && (
                <button onClick={() => (isPinned ? onUnpin(msg.id) : onPin(msg.id))} className="hover:text-accent">
                  {isPinned ? "Unpin" : "Pin"}
                </button>
              )}
              {canDelete && (
                <button onClick={() => onDelete(msg.id)} className="hover:text-danger">
                  Delete
                </button>
              )}
              <button onClick={() => onReport(msg.id)} className="hover:text-danger">
                Report
              </button>
            </span>
          )}
        </div>

        <span className="px-1 text-[10px] text-muted">
          {formatTime(msg.created_at)}
          {isPinned && " · 📌 pinned"}
        </span>
      </div>
    </div>
  );
}
