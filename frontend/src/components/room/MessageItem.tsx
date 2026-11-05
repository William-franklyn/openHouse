"use client";

import { useEffect, useRef, useState } from "react";
import { Pin, PinOff, Trash2, Flag, FileText, SmilePlus } from "lucide-react";
import { Avatar } from "@/components/ui/Avatar";
import { Tooltip } from "@/components/ui/Tooltip";
import { api } from "@/lib/api";
import { DownloadResponse, MemberRole, MessageOut } from "@/lib/types";

// Mirrors backend/app/messages.py's REACTION_EMOJI exactly - a fixed
// reaction-bar set rather than a full emoji picker, same "small curated
// set, no free text" tradeoff the server enforces.
const REACTION_EMOJI = ["👍", "❤️", "😂", "😮", "😢", "🔥", "🎉", "👀"];

function ReactionPicker({ onPick, onClose }: { onPick: (emoji: string) => void; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [onClose]);

  return (
    <div
      ref={ref}
      className="absolute right-0 top-full z-10 mt-1 flex gap-0.5 rounded-[var(--radius-sm)] border border-border bg-surface p-1 shadow-[var(--shadow-md)]"
    >
      {REACTION_EMOJI.map((emoji) => (
        <button
          key={emoji}
          type="button"
          onClick={() => {
            onPick(emoji);
            onClose();
          }}
          aria-label={`React with ${emoji}`}
          className="flex h-8 w-8 items-center justify-center rounded text-base hover:bg-surface-muted"
        >
          {emoji}
        </button>
      ))}
    </div>
  );
}

// Only matches explicit http(s) URLs - never bare "javascript:" or other
// schemes, so there's no way user-typed text can produce a dangerous href.
const URL_PATTERN = /(https?:\/\/[^\s<]+)/g;
// Trailing characters that are almost always sentence punctuation rather
// than part of the URL itself (e.g. "check this out: https://x.com." or
// "(see https://x.com)") - stripped from the link, rendered as plain text
// right after it so the sentence still reads correctly.
const TRAILING_PUNCTUATION = /[.,;:!?'")\]]+$/;

function Linkified({ text }: { text: string }) {
  const parts = text.split(URL_PATTERN);
  return (
    <>
      {parts.map((part, i) => {
        if (i % 2 === 0) return part;
        const trailingMatch = part.match(TRAILING_PUNCTUATION);
        const trailing = trailingMatch ? trailingMatch[0] : "";
        const url = trailing ? part.slice(0, -trailing.length) : part;
        return (
          <span key={i}>
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="break-all text-accent underline hover:no-underline"
            >
              {url}
            </a>
            {trailing}
          </span>
        );
      })}
    </>
  );
}

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
// PDFs are the one non-image/audio type browsers can render natively -
// everything else in ALLOWED_FILE_EXTENSIONS (doc/docx/txt/odt/zip) has
// no browser-native viewer and would just download regardless, so only
// PDFs get the "open" treatment instead of a forced download.
const PDF_EXT = /\.pdf$/i;

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

  const isPdf = PDF_EXT.test(info.filename);
  return (
    <a
      href={info.url}
      download={isPdf ? undefined : info.filename}
      target="_blank"
      rel="noreferrer"
      className="mt-1 inline-flex max-w-xs items-center gap-2.5 rounded-[var(--radius-md)] border border-border bg-surface-muted px-3 py-2 transition-colors hover:bg-sidebar-hover"
    >
      <FileText size={18} className="shrink-0 text-muted" />
      <span className="flex min-w-0 flex-col">
        <span className="truncate text-[13px] font-medium text-foreground">{info.filename}</span>
        <span className="text-[11px] text-muted">
          {formatSize(info.size)} · {isPdf ? "Opens in a new tab" : "Downloads"}
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
  onToggleReaction,
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
  onToggleReaction: (messageId: string, emoji: string) => void;
}) {
  const [pickerOpen, setPickerOpen] = useState(false);

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
            <Linkified text={msg.text ?? ""} />
          </p>
        )}
        {msg.reactions.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1">
            {msg.reactions.map((r) => {
              const mine = myMemberId !== null && r.member_ids.includes(myMemberId);
              return (
                <button
                  key={r.emoji}
                  type="button"
                  onClick={() => onToggleReaction(msg.id, r.emoji)}
                  className={`flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[12px] transition-colors ${
                    mine
                      ? "border-accent bg-accent-soft text-accent"
                      : "border-border bg-surface-muted text-muted hover:border-accent/50"
                  }`}
                >
                  <span>{r.emoji}</span>
                  <span className="text-[11px] font-medium">{r.member_ids.length}</span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {(canPin || canDelete || !isMine) && (
        <div className="absolute right-3 top-0 hidden -translate-y-1/2 items-center gap-0.5 rounded-[var(--radius-sm)] border border-border bg-surface p-0.5 shadow-[var(--shadow-sm)] group-hover:flex">
          <div className="relative">
            <Tooltip label="React">
              <button
                type="button"
                onClick={() => setPickerOpen((v) => !v)}
                aria-label="Add reaction"
                className="flex h-7 w-7 items-center justify-center rounded text-muted hover:bg-surface-muted hover:text-accent"
              >
                <SmilePlus size={14} />
              </button>
            </Tooltip>
            {pickerOpen && (
              <ReactionPicker
                onPick={(emoji) => onToggleReaction(msg.id, emoji)}
                onClose={() => setPickerOpen(false)}
              />
            )}
          </div>
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
