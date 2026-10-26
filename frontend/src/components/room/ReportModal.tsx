"use client";

import { FormEvent, useState } from "react";
import { CheckCircle2 } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/types";

export function ReportModal({
  open,
  onClose,
  roomId,
  token,
  target,
}: {
  open: boolean;
  onClose: () => void;
  roomId: string;
  token: string;
  target: { memberId?: string; messageId?: string } | null;
}) {
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!target) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.report(roomId, token, {
        reason,
        target_member_id: target.memberId ?? null,
        message_id: target.messageId ?? null,
      });
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't send the report.");
    } finally {
      setSubmitting(false);
    }
  }

  function handleClose() {
    setReason("");
    setDone(false);
    setError(null);
    onClose();
  }

  return (
    <Modal open={open} onClose={handleClose} title="Report">
      {done ? (
        <div className="flex flex-col items-center gap-3 py-2 text-center">
          <div className="flex h-11 w-11 items-center justify-center rounded-full bg-success/10">
            <CheckCircle2 size={22} className="text-success" />
          </div>
          <p className="text-sm text-muted">
            Thanks - this has been sent to the room&apos;s house owner and moderators.
          </p>
          <Button className="w-full" onClick={handleClose}>
            Close
          </Button>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <Input
            label="What happened?"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Describe the issue"
            required
            autoFocus
          />
          {error && <p className="text-sm text-danger">{error}</p>}
          <Button type="submit" disabled={submitting || !reason.trim()}>
            {submitting ? "Sending…" : "Send report"}
          </Button>
        </form>
      )}
    </Modal>
  );
}
