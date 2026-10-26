"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowDown, Hash } from "lucide-react";
import { api } from "@/lib/api";
import { getBlockedIds } from "@/lib/blocked";
import { useRoomStore } from "@/lib/store";
import { MessageItem } from "./MessageItem";
import { MessageOut } from "@/lib/types";

// A stable reference for "no messages yet" - `?? []` would allocate a new
// array every render, which breaks useSyncExternalStore's snapshot
// comparison (every render looks "changed") and causes an infinite loop.
const EMPTY_MESSAGES: MessageOut[] = [];

const GROUP_WINDOW_MS = 5 * 60 * 1000;

export function MessageList({
  roomId,
  channelId,
  token,
  onPin,
  onUnpin,
  onDeleteMessage,
  onReportMessage,
}: {
  roomId: string;
  channelId: string;
  token: string;
  onPin: (messageId: string) => void;
  onUnpin: (messageId: string) => void;
  onDeleteMessage: (messageId: string) => void;
  onReportMessage: (messageId: string) => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [blocked, setBlocked] = useState<Set<string>>(new Set());
  const [loadingMore, setLoadingMore] = useState(false);
  const [exhausted, setExhausted] = useState(false);
  const [showJumpToBottom, setShowJumpToBottom] = useState(false);

  const messages = useRoomStore((s) => s.messagesByChannel[channelId] ?? EMPTY_MESSAGES);
  const pinnedIds = useRoomStore((s) => s.pinnedIds);
  const myRole = useRoomStore((s) => s.myRole);
  const myMemberId = useRoomStore((s) => s.myMemberId);
  const channelName = useRoomStore((s) => s.channels.find((c) => c.id === channelId)?.name ?? "");

  useEffect(() => {
    setBlocked(getBlockedIds());
  }, []);

  // Keep scrolled to bottom when new messages arrive, unless the user has
  // scrolled up to read history (then don't yank them back down).
  const prevLengthRef = useRef(messages.length);
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const grew = messages.length > prevLengthRef.current;
    prevLengthRef.current = messages.length;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 200;
    if (grew && nearBottom) {
      el.scrollTop = el.scrollHeight;
    }
    setShowJumpToBottom(!nearBottom && messages.length > 0);
  }, [messages.length]);

  async function loadMore() {
    if (loadingMore || exhausted || messages.length === 0) return;
    setLoadingMore(true);
    try {
      const earliest = messages[0].seq;
      const res = await api.history(roomId, channelId, token, earliest);
      if (res.messages.length === 0) setExhausted(true);
      useRoomStore.getState().prependHistory(channelId, res.messages);
    } finally {
      setLoadingMore(false);
    }
  }

  function handleScroll() {
    const el = scrollRef.current;
    if (!el) return;
    if (el.scrollTop < 80) loadMore();
    setShowJumpToBottom(el.scrollHeight - el.scrollTop - el.clientHeight > 300);
  }

  function jumpToBottom() {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }

  const visible = messages.filter((m) => !m.member_id || !blocked.has(m.member_id));

  return (
    <div className="relative flex-1 overflow-hidden">
      <div ref={scrollRef} onScroll={handleScroll} className="h-full overflow-y-auto px-3 py-3 sm:px-4">
        {visible.length === 0 && !loadingMore && (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-accent-soft">
              <Hash size={22} className="text-accent" />
            </div>
            <h3 className="mt-2 text-[15px] font-semibold text-foreground">
              Welcome to #{channelName}
            </h3>
            <p className="max-w-xs text-[13px] text-muted">
              This is the start of the channel. Say hi to get the conversation going.
            </p>
          </div>
        )}

        {visible.map((msg, i) => {
          const prev = visible[i - 1];
          const showHeader =
            !prev ||
            prev.kind === "system" ||
            prev.member_id !== msg.member_id ||
            new Date(msg.created_at).getTime() - new Date(prev.created_at).getTime() > GROUP_WINDOW_MS;

          return (
            <div key={msg.id} className="animate-message-in">
              <MessageItem
                msg={msg}
                token={token}
                myRole={myRole}
                myMemberId={myMemberId}
                showHeader={showHeader}
                isPinned={pinnedIds.includes(msg.id)}
                onPin={onPin}
                onUnpin={onUnpin}
                onDelete={onDeleteMessage}
                onReport={onReportMessage}
              />
            </div>
          );
        })}
      </div>

      {showJumpToBottom && (
        <button
          onClick={jumpToBottom}
          className="absolute bottom-3 left-1/2 flex -translate-x-1/2 animate-slide-up items-center gap-1.5 rounded-full bg-surface px-3.5 py-2 text-[12px] font-medium text-foreground shadow-[var(--shadow-md)] ring-1 ring-border transition-transform hover:-translate-y-0.5"
        >
          <ArrowDown size={13} />
          New messages
        </button>
      )}
    </div>
  );
}
