"use client";

import { useEffect, useState } from "react";
import { Pin, PinOff, Trash2, Flag, FileText } from "lucide-react";
import { Avatar } from "@/components/ui/Avatar";
import { Tooltip } from "@/components/ui/Tooltip";
import { api } from "@/lib/api";
import { DownloadResponse, MemberRole, MessageOut } from "@/lib/types";

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

function formatHourMinute(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
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

function FileMessage({ msg, token }: { msg: MessageOut; token: string }) {
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
      <div className="flex items-center gap-2 text-sm text-muted">
        <span className="h-3 w-3 animate-pulse rounded-full bg-current" />
        Loading…
      </div>
    );
  }

  if (AUDIO_EXT.test(info.filename)) {
    return (
      <div className="mt-1 flex flex-col gap-1">
        <audio controls src={info.url} className="h-10 w-72 max-w-full" />
        <span className="text-[11px] text-muted">Voice message · {formatSize(info.size)}</span>
      </div>
    );
  }

  if (IMAGE_EXT.test(info.filename)) {
    return (
      <a
        href={info.url}
        target="_blank"
        rel="noreferrer"
        className="mt-1 block w-fit overflow-hidden rounded-[var(--radius-md)] border border-border"
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={info.url} alt={info.filename} className="max-h-72 max-w-full object-cover" />
      </a>
    );
  }

  return (
    <a
      href={info.url}
      download={info.filename}
      target="_blank"
      rel="noreferrer"
      className="mt-1 inline-flex max-w-xs items-center gap-2.5 rounded-[var(--radius-md)] border border-border bg-surface-muted px-3 py-2 transition-colors hover:bg-sidebar-hover"
    >
      <FileText size={18} className="shrink-0 text-muted" />
      <span className="flex min-w-0 flex-col">
        <span className="truncate text-[13px] font-medium text-foreground">{info.filename}</span>
        <span className="text-[11px] text-muted">{formatSize(info.size)}</span>
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
      <div className="flex justify-center py-1.5">
        <span className="rounded-full bg-surface-muted px-3 py-1 text-[11px] text-muted">{msg.text}</span>
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
      className={`group relative flex gap-3 rounded-[var(--radius-sm)] px-3 py-0.5 hover:bg-surface-muted/70 sm:px-4 ${
        showHeader ? "mt-3" : "mt-0"
      }`}
    >
      <div className="w-9 shrink-0 pt-0.5 text-center">
        {showHeader ? (
          <Avatar name={name} seed={msg.member_id ?? name} size="md" />
        ) : (
          <span className="hidden pt-0.5 text-[10px] leading-none text-muted group-hover:inline-block">
            {formatHourMinute(msg.created_at)}
          </span>
        )}
      </div>

      <div className="min-w-0 flex-1 pb-0.5">
        {showHeader && (
          <div className="flex items-baseline gap-2">
            <span className="text-[14px] font-semibold text-foreground">{name}</span>
            <span className="text-[11px] text-muted">{formatTime(msg.created_at)}</span>
            {isPinned && (
              <span className="flex items-center gap-1 text-[11px] text-accent">
                <Pin size={11} /> Pinned
              </span>
            )}
          </div>
        )}
        {msg.kind === "file" ? (
          <FileMessage msg={msg} token={token} />
        ) : (
          <p className="whitespace-pre-wrap break-words text-[14px] leading-relaxed text-foreground">
            {msg.text}
          </p>
        )}
      </div>

      {(canPin || canDelete || !isMine) && (
        <div className="absolute right-3 top-0 hidden -translate-y-1/2 items-center gap-0.5 rounded-[var(--radius-sm)] border border-border bg-surface p-0.5 shadow-[var(--shadow-sm)] group-hover:flex">
          {canPin && (
            <Tooltip label={isPinned ? "Unpin" : "Pin"}>
              <button
                onClick={() => (isPinned ? onUnpin(msg.id) : onPin(msg.id))}
                aria-label={isPinned ? "Unpin message" : "Pin message"}
                className="flex h-7 w-7 items-center justify-center rounded text-muted hover:bg-surface-muted hover:text-accent"
              >
                {isPinned ? <PinOff size={14} /> : <Pin size={14} />}
              </button>
            </Tooltip>
          )}
          {canDelete && (
            <Tooltip label="Delete">
              <button
                onClick={() => onDelete(msg.id)}
                aria-label="Delete message"
                className="flex h-7 w-7 items-center justify-center rounded text-muted hover:bg-danger-soft hover:text-danger"
              >
                <Trash2 size={14} />
              </button>
            </Tooltip>
          )}
          {!isMine && (
            <Tooltip label="Report">
              <button
                onClick={() => onReport(msg.id)}
                aria-label="Report message"
                className="flex h-7 w-7 items-center justify-center rounded text-muted hover:bg-danger-soft hover:text-danger"
              >
                <Flag size={14} />
              </button>
            </Tooltip>
          )}
        </div>
      )}
    </div>
  );
}
