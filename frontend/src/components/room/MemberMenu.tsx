"use client";

import { useState } from "react";
import { Ban, Shield, ShieldOff, Crown, UserX, Flag, UserRoundX } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Avatar } from "@/components/ui/Avatar";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { blockMember, getBlockedIds, unblockMember } from "@/lib/blocked";
import { roleLabel } from "@/lib/roleLabel";
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
  const [confirmingBan, setConfirmingBan] = useState(false);

  if (!member) return null;
  const isSelf = member.member_id === myMemberId;
  const canModerate =
    !isSelf && (myRole === "owner" || (myRole === "mod" && member.role === "member"));
  const isOwner = myRole === "owner";

  function handleClose() {
    setConfirmingBan(false);
    onClose();
  }

  return (
    <Modal open={open} onClose={handleClose}>
      <div className="flex flex-col items-center gap-2 pb-1 text-center">
        <Avatar name={member.name} seed={member.member_id} size="lg" />
        <h2 className="text-[16px] font-semibold text-foreground">{member.name}</h2>
        <Badge tone={member.role === "owner" ? "accent" : "default"}>{roleLabel(member.role)}</Badge>
      </div>

      <div className="mt-4 flex flex-col gap-1.5">
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
              <UserX size={15} />
              {blocked ? "Unblock" : "Block"}
            </Button>
            <Button variant="secondary" onClick={() => onReport(member.member_id)}>
              <Flag size={15} />
              Report
            </Button>
          </>
        )}

        {isOwner && !isSelf && member.role !== "owner" && (
          <Button
            variant="secondary"
            onClick={() => onPromote(member.member_id, member.role === "mod" ? "member" : "mod")}
          >
            {member.role === "mod" ? <ShieldOff size={15} /> : <Shield size={15} />}
            {member.role === "mod" ? "Remove moderator" : "Make moderator"}
          </Button>
        )}

        {isOwner && !isSelf && (
          <Button variant="secondary" onClick={() => onOfferOwnership(member.member_id)}>
            <Crown size={15} />
            Make house owner
          </Button>
        )}

        {canModerate && (
          <>
            <div className="my-1 h-px bg-border" />
            <Button variant="secondary" onClick={() => onKick(member.member_id)}>
              <UserRoundX size={15} />
              Remove from room
            </Button>

            {confirmingBan ? (
              <div className="flex flex-col gap-2 rounded-[var(--radius-md)] bg-danger-soft p-3">
                <p className="text-[13px] text-foreground">
                  Ban {member.name}? They won&apos;t be able to rejoin with this device or session.
                </p>
                <div className="flex gap-2">
                  <Button variant="secondary" size="sm" className="flex-1" onClick={() => setConfirmingBan(false)}>
                    Cancel
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    className="flex-1 border-danger bg-danger text-white hover:bg-danger/90"
                    onClick={() => onBan(member.member_id)}
                  >
                    Confirm ban
                  </Button>
                </div>
              </div>
            ) : (
              <Button variant="danger" onClick={() => setConfirmingBan(true)}>
                <Ban size={15} />
                Ban
              </Button>
            )}
          </>
        )}
      </div>
    </Modal>
  );
}
