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
  roomCode,
  token,
}: {
  open: boolean;
  onClose: () => void;
  roomId: string;
  roomCode: string;
  token: string;
}) {
  const [code, setCode] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState<"link" | "code" | null>(null);

  const link =
    code && typeof window !== "undefined"
      ? `${window.location.origin}/r/${roomCode}?invite=${code}`
      : "";

  function copy(value: string, which: "link" | "code") {
    navigator.clipboard?.writeText(value).then(() => {
      setCopied(which);
      setTimeout(() => setCopied(null), 1500);
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
        <div className="flex flex-col gap-4">
          <div>
            <p className="mb-1.5 text-sm font-medium">Send this link</p>
            <div className="break-all rounded-lg bg-surface-muted px-3 py-2.5 text-sm">{link}</div>
            <button type="button" onClick={() => copy(link, "link")} className="mt-1.5 text-sm text-accent underline">
              {copied === "link" ? "Copied!" : "Copy link"}
            </button>
          </div>

          <details className="text-sm">
            <summary className="cursor-pointer text-muted">Or share the code manually</summary>
            <div className="mt-2 flex flex-col items-center gap-1.5 text-center">
              <div className="w-full break-all rounded-lg bg-surface-muted px-3 py-2 font-mono text-sm font-semibold tracking-wide">
                {code}
              </div>
              <p className="text-xs text-muted">
                They&apos;ll need this room&apos;s link too - this code alone can&apos;t get them in.
              </p>
              <button type="button" onClick={() => copy(code, "code")} className="text-sm text-accent underline">
                {copied === "code" ? "Copied!" : "Copy code"}
              </button>
            </div>
          </details>

          <p className="text-sm text-muted">Valid for 15 minutes, one person.</p>
          <Button className="w-full" onClick={handleClose}>
            Done
          </Button>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {error && <p className="text-sm text-danger">{error}</p>}
          <Button onClick={createInvite} disabled={loading}>
            {loading ? "Creating…" : "Generate invite link"}
          </Button>
        </div>
      )}
    </Modal>
  );
}
