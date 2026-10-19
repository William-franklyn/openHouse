"use client";

import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";

export function DeleteRoomDialog({
  open,
  onClose,
  roomName,
  onConfirm,
}: {
  open: boolean;
  onClose: () => void;
  roomName: string;
  onConfirm: () => void;
}) {
  const [typed, setTyped] = useState("");

  return (
    <Modal open={open} onClose={onClose} title="Delete this room">
      <p className="text-sm text-muted">
        This disconnects everyone and permanently erases all messages and files. Type{" "}
        <strong className="text-foreground">{roomName}</strong> to confirm.
      </p>
      <Input
        className="mt-3"
        value={typed}
        onChange={(e) => setTyped(e.target.value)}
        placeholder={roomName}
        autoFocus
      />
      <Button
        variant="danger"
        className="mt-4 w-full"
        disabled={typed !== roomName}
        onClick={onConfirm}
      >
        Delete room permanently
      </Button>
    </Modal>
  );
}
