"use client";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { useRoomStore } from "@/lib/store";

export function OwnershipOfferModal({
  fromName,
  onAnswer,
}: {
  fromName: string | null;
  onAnswer: (accept: boolean) => void;
}) {
  return (
    <Modal
      open={fromName !== null}
      onClose={() => {
        onAnswer(false);
        useRoomStore.getState().setOwnershipOffer(null);
      }}
      title="House owner offer"
    >
      <p className="text-sm text-muted">
        {fromName} wants to make you the house owner of this room. You&apos;ll get full control, and{" "}
        {fromName} becomes a regular member.
      </p>
      <div className="mt-4 flex gap-2">
        <Button
          variant="secondary"
          className="flex-1"
          onClick={() => {
            onAnswer(false);
            useRoomStore.getState().setOwnershipOffer(null);
          }}
        >
          Decline
        </Button>
        <Button className="flex-1" onClick={() => onAnswer(true)}>
          Accept
        </Button>
      </div>
    </Modal>
  );
}
