"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ApiError, DownloadResponse, MemberRole, MessageOut } from "@/lib/types";

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

  if (error) return <p className="text-sm text-danger">Couldn&apos;t load this file.</p>;
  if (!info) return <p className="text-sm text-muted">Loading file…</p>;

  const isImage = /\.(png|jpe?g|gif|webp)$/i.test(info.filename);

  return (
    <a
      href={info.url}
      download={info.filename}
      target="_blank"
      rel="noreferrer"
      className="inline-flex max-w-xs flex-col gap-2 rounded-lg border border-border bg-surface-muted p-2"
    >
      {isImage && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={info.url} alt={info.filename} className="max-h-48 rounded object-cover" />
      )}
      <span className="truncate text-sm font-medium text-accent">{info.filename}</span>
      <span className="text-xs text-muted">{formatSize(info.size)}</span>
    </a>
  );
}

export function MessageItem({
  msg,
  token,
  myRole,
  myMemberId,
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
  isPinned: boolean;
  onPin: (messageId: string) => void;
  onUnpin: (messageId: string) => void;
  onDelete: (messageId: string) => void;
  onReport: (messageId: string) => void;
}) {
  if (msg.kind === "system") {
    return <p className="py-1 text-center text-xs italic text-muted">{msg.text}</p>;
  }

  const isAdmin = myRole === "owner" || myRole === "mod";
  const isMine = msg.member_id === myMemberId;
  const canDelete = isMine || isAdmin;
  const canPin = isAdmin;

  return (
    <div className="group flex flex-col gap-1 py-1.5">
      <div className="flex items-baseline gap-2">
        <span className="text-sm font-semibold">{msg.from_name ?? "Someone"}</span>
        <span className="text-xs text-muted">{formatTime(msg.created_at)}</span>
        {isPinned && <span className="text-xs text-accent">📌 pinned</span>}
        <span className="ml-auto hidden gap-2 text-xs text-muted group-hover:flex">
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
          {!isMine && (
            <button onClick={() => onReport(msg.id)} className="hover:text-danger">
              Report
            </button>
          )}
        </span>
      </div>
      {msg.kind === "file" ? (
        <FileMessage msg={msg} token={token} />
      ) : (
        <p className="whitespace-pre-wrap break-words text-sm">{msg.text}</p>
      )}
    </div>
  );
}
