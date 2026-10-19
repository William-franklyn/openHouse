"use client";

import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { blockMember, getBlockedIds, unblockMember } from "@/lib/blocked";
import { MemberRole } from "@/lib/types";

export function MemberMenu({
  open,
  onClose,
  member,
  myRole,
  myMemberId,
  onKick,
  onBan,
  onPromote,
  onOfferOwnership,
  onReport,
}: {
  open: boolean;
  onClose: () => void;
  member: { member_id: string; name: string; role: MemberRole } | null;
  myRole: MemberRole | null;
  myMemberId: string | null;
  onKick: (memberId: string) => void;
  onBan: (memberId: string) => void;
  onPromote: (memberId: string, role: "mod" | "member") => void;
  onOfferOwnership: (memberId: string) => void;
  onReport: (memberId: string) => void;
}) {
  const [blocked, setBlocked] = useState(() => (member ? getBlockedIds().has(member.member_id) : false));

  if (!member) return null;
  const isSelf = member.member_id === myMemberId;
  const canModerate =
    !isSelf && (myRole === "owner" || (myRole === "mod" && member.role === "member"));
  const isOwner = myRole === "owner";

  return (
    <Modal open={open} onClose={onClose} title={member.name}>
      <div className="flex flex-col gap-2">
        <div className="mb-2">
          <Badge tone={member.role === "owner" ? "accent" : "default"}>{member.role}</Badge>
        </div>

        {!isSelf && (
          <>
            <Button
              variant="secondary"
              onClick={() => {
                if (blocked) {
                  unblockMember(member.member_id);
                  setBlocked(false);
                } else {
                  blockMember(member.member_id);
                  setBlocked(true);
                }
              }}
            >
              {blocked ? "Unblock" : "Block"}
            </Button>
            <Button variant="secondary" onClick={() => onReport(member.member_id)}>
              Report
            </Button>
          </>
        )}

        {canModerate && (
          <>
            <Button variant="secondary" onClick={() => onKick(member.member_id)}>
              Remove from room
            </Button>
            <Button variant="danger" onClick={() => onBan(member.member_id)}>
              Ban
            </Button>
          </>
        )}

        {isOwner && !isSelf && member.role !== "owner" && (
          <Button
            variant="secondary"
            onClick={() => onPromote(member.member_id, member.role === "mod" ? "member" : "mod")}
          >
            {member.role === "mod" ? "Remove moderator" : "Make moderator"}
          </Button>
        )}

        {isOwner && !isSelf && (
          <Button variant="secondary" onClick={() => onOfferOwnership(member.member_id)}>
            Offer ownership
          </Button>
        )}
      </div>
    </Modal>
  );
}
