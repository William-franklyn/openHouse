"use client";

import { useState } from "react";
import { useRoomStore } from "@/lib/store";
import { Badge } from "@/components/ui/Badge";
import { MemberMenu } from "./MemberMenu";
import { PresenceMember } from "@/lib/types";

export function OnlineList({
  onKick,
  onBan,
  onPromote,
  onOfferOwnership,
  onReport,
}: {
  onKick: (memberId: string) => void;
  onBan: (memberId: string) => void;
  onPromote: (memberId: string, role: "mod" | "member") => void;
  onOfferOwnership: (memberId: string) => void;
  onReport: (memberId: string) => void;
}) {
  const online = useRoomStore((s) => s.online);
  const myRole = useRoomStore((s) => s.myRole);
  const myMemberId = useRoomStore((s) => s.myMemberId);
  const [selected, setSelected] = useState<PresenceMember | null>(null);

  return (
    <aside className="flex w-full flex-col gap-1 overflow-y-auto border-l border-border p-3 sm:w-56">
      <h2 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">
        Online — {online.length}
      </h2>
      {online.map((m) => (
        <button
          key={m.member_id}
          onClick={() => setSelected(m)}
          className="flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-surface-muted"
        >
          <span className="truncate">{m.name}</span>
          {m.role !== "member" && <Badge tone={m.role === "owner" ? "accent" : "default"}>{m.role}</Badge>}
        </button>
      ))}

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
    </aside>
  );
}
