"use client";

import { Modal } from "@/components/ui/Modal";
import { Avatar } from "@/components/ui/Avatar";
import { useRoomStore } from "@/lib/store";

export function StartGameModal({
  open,
  onClose,
  myMemberId,
  onChallenge,
}: {
  open: boolean;
  onClose: () => void;
  myMemberId: string;
  onChallenge: (opponentId: string) => void;
}) {
  const online = useRoomStore((s) => s.online);
  const others = online.filter((m) => m.member_id !== myMemberId);

  function pick(memberId: string) {
    onChallenge(memberId);
    onClose();
  }

  return (
    <Modal open={open} onClose={onClose} title="♟️ Play chess">
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
      </div>
    </Modal>
  );
}
