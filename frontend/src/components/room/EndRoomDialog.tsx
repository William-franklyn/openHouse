"use client";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";

export function EndRoomDialog({
  open,
  onClose,
  onConfirm,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
}) {
  return (
    <Modal open={open} onClose={onClose} title="End this room now">
      <p className="text-sm text-muted">
        Disconnects everyone right away. Unlike deleting, the chat history and files are kept -
        you can reopen the room later by clearing &quot;Ends at&quot; in settings.
      </p>
      <Button variant="danger" className="mt-4 w-full" onClick={onConfirm}>
        End room now
      </Button>
    </Modal>
  );
}
