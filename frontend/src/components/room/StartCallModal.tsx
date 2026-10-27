"use client";

import { useState } from "react";
import { Phone } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Avatar } from "@/components/ui/Avatar";
import { useRoomStore } from "@/lib/store";

export function StartCallModal({
  open,
  onClose,
  myMemberId,
  onStart,
}: {
  open: boolean;
  onClose: () => void;
  myMemberId: string;
  onStart: (inviteeIds: string[]) => void;
}) {
  const online = useRoomStore((s) => s.online);
  const [selected, setSelected] = useState<string[]>([]);

  const others = online.filter((m) => m.member_id !== myMemberId);

  function toggle(memberId: string) {
    setSelected((prev) =>
      prev.includes(memberId) ? prev.filter((id) => id !== memberId) : [...prev, memberId]
    );
  }

  function handleStart() {
    if (selected.length === 0) return;
    onStart(selected);
    setSelected([]);
    onClose();
  }

  return (
    <Modal open={open} onClose={onClose} title="Start a video call">
      <div className="flex flex-col gap-3">
        <p className="text-[13px] text-muted">
          Pick who to invite. They&apos;ll get a prompt to join - only people here will be in the
          same call.
        </p>

        <div className="flex max-h-64 flex-col gap-0.5 overflow-y-auto rounded-[var(--radius-md)] border border-border p-1.5">
          {others.length === 0 ? (
            <p className="px-2 py-4 text-center text-[13px] text-muted">No one else is online right now.</p>
          ) : (
            others.map((m) => {
              const checked = selected.includes(m.member_id);
              return (
                <button
                  key={m.member_id}
                  type="button"
                  onClick={() => toggle(m.member_id)}
                  aria-pressed={checked}
                  className={`flex w-full items-center gap-2.5 rounded-[var(--radius-sm)] px-2.5 py-2 text-left transition-colors ${
                    checked ? "bg-accent-soft" : "hover:bg-surface-muted"
                  }`}
                >
                  <Avatar name={m.name} seed={m.member_id} size="sm" />
                  <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-foreground">
                    {m.name}
                  </span>
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggle(m.member_id)}
                    className="h-4 w-4 shrink-0 accent-accent"
                    tabIndex={-1}
                  />
                </button>
              );
            })
          )}
        </div>

        <Button onClick={handleStart} disabled={selected.length === 0}>
          <Phone size={15} />
          {selected.length === 0
            ? "Start call"
            : `Call ${selected.length} ${selected.length === 1 ? "person" : "people"}`}
        </Button>
      </div>
    </Modal>
  );
}
