"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { useRoomStore } from "@/lib/store";
import { Avatar } from "@/components/ui/Avatar";
import { Badge } from "@/components/ui/Badge";
import { roleLabel } from "@/lib/roleLabel";
import { MemberMenu } from "./MemberMenu";
import { PresenceMember } from "@/lib/types";

function MemberListPanel({ onClose, onSelect }: { onClose: () => void; onSelect: (m: PresenceMember) => void }) {
  const online = useRoomStore((s) => s.online);

  return (
    <div className="flex h-full w-[248px] flex-col border-l border-border bg-surface">
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-border px-4">
        <h2 className="text-[13px] font-semibold text-foreground">Members — {online.length}</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close members panel"
          className="flex h-7 w-7 items-center justify-center rounded text-muted hover:bg-surface-muted xl:hidden"
        >
          <X size={15} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {online.length === 0 ? (
          <p className="px-2 py-4 text-center text-[13px] text-muted">No one else is here yet.</p>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {online.map((m) => (
              <li key={m.member_id}>
                <button
                  type="button"
                  onClick={() => onSelect(m)}
                  className="flex w-full items-center gap-2.5 rounded-[var(--radius-sm)] px-2 py-1.5 text-left transition-colors hover:bg-surface-muted"
                >
                  <span className="relative shrink-0">
                    <Avatar name={m.name} seed={m.member_id} size="sm" />
                    <span className="absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full border-2 border-surface bg-success" />
                  </span>
                  <span className="min-w-0 flex-1 truncate text-[13px] text-foreground">{m.name}</span>
                  {m.role !== "member" && (
                    <Badge tone={m.role === "owner" ? "accent" : "default"}>{roleLabel(m.role)}</Badge>
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export function OnlineList({
  open,
  onClose,
  onKick,
  onBan,
  onPromote,
  onOfferOwnership,
  onReport,
}: {
  open: boolean;
  onClose: () => void;
  onKick: (memberId: string) => void;
  onBan: (memberId: string) => void;
  onPromote: (memberId: string, role: "mod" | "member") => void;
  onOfferOwnership: (memberId: string) => void;
  onReport: (memberId: string) => void;
}) {
  const myRole = useRoomStore((s) => s.myRole);
  const myMemberId = useRoomStore((s) => s.myMemberId);
  const [selected, setSelected] = useState<PresenceMember | null>(null);

  return (
    <>
      {/* Large screens: static column, toggled by the parent. Small
          screens: off-canvas drawer from the right. These must stay as
          two separate mount points rather than one shared JSX variable
          rendered twice - duplicating a subtree that owns a <dialog>
          (MemberMenu, below) would create two independent dialog
          instances reacting to the same `open` state, both calling
          showModal() at once. MemberMenu is hoisted out and rendered
          exactly once for that reason. */}
      {open && (
        <div className="hidden xl:block">
          <MemberListPanel onClose={onClose} onSelect={setSelected} />
        </div>
      )}

      {open && (
        <div className="fixed inset-0 z-40 xl:hidden">
          <div className="absolute inset-0 animate-fade-in bg-[#191b2a]/45" onClick={onClose} aria-hidden />
          <div className="absolute inset-y-0 right-0 w-[248px] animate-slide-in-right bg-surface shadow-[var(--shadow-lg)]">
            <MemberListPanel onClose={onClose} onSelect={setSelected} />
          </div>
        </div>
      )}

      <MemberMenu
        open={selected !== null}
        onClose={() => setSelected(null)}
        member={selected}
        myRole={myRole}
        myMemberId={myMemberId}
        onKick={(id) => {
          onKick(id);
          setSelected(null);
        }}
        onBan={(id) => {
          onBan(id);
          setSelected(null);
        }}
        onPromote={(id, role) => {
          onPromote(id, role);
          setSelected(null);
        }}
        onOfferOwnership={(id) => {
          onOfferOwnership(id);
          setSelected(null);
        }}
        onReport={(id) => {
          onReport(id);
          setSelected(null);
        }}
      />
    </>
  );
}
