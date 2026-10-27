"use client";

import { Phone, PhoneOff } from "lucide-react";
import { useRoomStore } from "@/lib/store";

export function IncomingCallToast() {
  const invite = useRoomStore((s) => s.incomingCallInvite);

  if (!invite) return null;

  function accept() {
    useRoomStore.getState().setMyCallId(invite!.callId);
    useRoomStore.getState().setIncomingCallInvite(null);
  }

  function dismiss() {
    useRoomStore.getState().setIncomingCallInvite(null);
  }

  return (
    <div className="animate-slide-up fixed bottom-[max(1rem,env(safe-area-inset-bottom))] left-1/2 z-[60] w-[min(92vw,360px)] -translate-x-1/2 rounded-[var(--radius-lg)] border border-border bg-surface p-3.5 shadow-[var(--shadow-lg)]">
      <div className="flex items-center gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent">
          <Phone size={16} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-semibold text-foreground">{invite.hostName}</p>
          <p className="text-[12px] text-muted">is inviting you to a video call</p>
        </div>
      </div>
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          onClick={dismiss}
          className="flex flex-1 items-center justify-center gap-1.5 rounded-[var(--radius-md)] border border-border py-2 text-[13px] font-medium text-muted hover:bg-surface-muted"
        >
          <PhoneOff size={14} />
          Dismiss
        </button>
        <button
          type="button"
          onClick={accept}
          className="flex flex-1 items-center justify-center gap-1.5 rounded-[var(--radius-md)] bg-accent py-2 text-[13px] font-medium text-accent-foreground hover:bg-accent-hover"
        >
          <Phone size={14} />
          Join
        </button>
      </div>
    </div>
  );
}
