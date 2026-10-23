"use client";

import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/types";

export function InviteModal({
  open,
  onClose,
  roomId,
  token,
}: {
  open: boolean;
  onClose: () => void;
  roomId: string;
  token: string;
}) {
  const [code, setCode] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  function copyCode() {
    if (!code) return;
    navigator.clipboard?.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  async function createInvite() {
    setLoading(true);
    setError(null);
    try {
      const result = await api.createInvite(roomId, token);
      setCode(result.code);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't create an invite.");
    } finally {
      setLoading(false);
    }
  }

  function handleClose() {
    setCode(null);
    setError(null);
    onClose();
  }

  return (
    <Modal open={open} onClose={handleClose} title="Invite someone">
      {code ? (
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="w-full break-all rounded-lg bg-surface-muted px-3 py-3 font-mono text-lg font-semibold tracking-wide">
            {code}
          </div>
          <button type="button" onClick={copyCode} className="text-sm text-accent underline">
            {copied ? "Copied!" : "Copy code"}
          </button>
          <p className="text-sm text-muted">Valid for 15 minutes, one person.</p>
          <Button className="mt-2 w-full" onClick={handleClose}>
            Done
          </Button>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {error && <p className="text-sm text-danger">{error}</p>}
          <Button onClick={createInvite} disabled={loading}>
            {loading ? "Creating…" : "Generate invite code"}
          </Button>
        </div>
      )}
    </Modal>
  );
}
