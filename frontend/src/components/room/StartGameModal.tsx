"use client";

import { Link2 } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Avatar } from "@/components/ui/Avatar";
import { useRoomStore } from "@/lib/store";
import { GAME_REGISTRY } from "@/lib/gameRegistry";
import { GameKind } from "@/lib/types";

export function StartGameModal({
  open,
  onClose,
  kind,
  myMemberId,
  onChallenge,
  onInviteLink,
}: {
  open: boolean;
  onClose: () => void;
  kind: GameKind;
  myMemberId: string;
  onChallenge: (opponentId: string) => void;
  onInviteLink: () => void;
}) {
  const online = useRoomStore((s) => s.online);
  const others = online.filter((m) => m.member_id !== myMemberId);
  const { emoji, label } = GAME_REGISTRY[kind];

  function pick(memberId: string) {
    onChallenge(memberId);
    onClose();
  }

  function pickLink() {
    onInviteLink();
    onClose();
  }

  return (
    <Modal open={open} onClose={onClose} title={`${emoji} Play ${label}`}>
      <div className="flex flex-col gap-3">
        <p className="text-[13px] text-muted">Pick who to challenge. They&apos;ll get a prompt to accept.</p>

        <div className="flex max-h-64 flex-col gap-0.5 overflow-y-auto rounded-[var(--radius-md)] border border-border p-1.5">
          {others.length === 0 ? (
            <p className="px-2 py-4 text-center text-[13px] text-muted">No one else is online right now.</p>
          ) : (
            others.map((m) => (
              <button
                key={m.member_id}
                type="button"
                onClick={() => pick(m.member_id)}
                className="flex w-full items-center gap-2.5 rounded-[var(--radius-sm)] px-2.5 py-2 text-left transition-colors hover:bg-surface-muted"
              >
                <Avatar name={m.name} seed={m.member_id} size="sm" />
                <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-foreground">{m.name}</span>
              </button>
            ))
          )}
        </div>

        <div className="flex items-center gap-2 text-[11px] text-muted before:h-px before:flex-1 before:bg-border after:h-px after:flex-1 after:bg-border">
          or
        </div>

        <button
          type="button"
          onClick={pickLink}
          className="flex w-full items-center gap-2.5 rounded-[var(--radius-md)] border border-accent/30 bg-accent-soft px-3 py-2.5 text-left transition-colors hover:border-accent"
        >
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent/15 text-accent">
            <Link2 size={14} />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-[13px] font-medium text-foreground">Invite a friend with a link</span>
            <span className="block text-[11px] text-muted">
              For someone who isn&apos;t in the room yet - share it anywhere
            </span>
          </span>
        </button>
      </div>
    </Modal>
  );
}
