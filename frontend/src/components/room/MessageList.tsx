"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { getBlockedIds } from "@/lib/blocked";
import { useRoomStore } from "@/lib/store";
import { MessageItem } from "./MessageItem";
import { MessageOut } from "@/lib/types";

// A stable reference for "no messages yet" - `?? []` would allocate a new
// array every render, which breaks useSyncExternalStore's snapshot
// comparison (every render looks "changed") and causes an infinite loop.
const EMPTY_MESSAGES: MessageOut[] = [];

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

  const messages = useRoomStore((s) => s.messagesByChannel[channelId] ?? EMPTY_MESSAGES);
  const pinnedIds = useRoomStore((s) => s.pinnedIds);
  const myRole = useRoomStore((s) => s.myRole);
  const myMemberId = useRoomStore((s) => s.myMemberId);

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
    if (scrollRef.current && scrollRef.current.scrollTop < 80) {
      loadMore();
    }
  }

  const visible = messages.filter((m) => !m.member_id || !blocked.has(m.member_id));

  return (
    <div ref={scrollRef} onScroll={handleScroll} className="flex-1 overflow-y-auto px-4 py-2">
      {visible.map((msg) => (
        <MessageItem
          key={msg.id}
          msg={msg}
          token={token}
          myRole={myRole}
          myMemberId={myMemberId}
          isPinned={pinnedIds.includes(msg.id)}
          onPin={onPin}
          onUnpin={onUnpin}
          onDelete={onDeleteMessage}
          onReport={onReportMessage}
        />
      ))}
    </div>
  );
}
