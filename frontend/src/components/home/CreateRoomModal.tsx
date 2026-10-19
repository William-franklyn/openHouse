"use client";

import { FormEvent, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";
import { getDeviceId } from "@/lib/device";
import { saveSession } from "@/lib/session";
import { ApiError, CreateRoomResponse } from "@/lib/types";

export function CreateRoomModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (result: CreateRoomResponse) => void;
}) {
  const [name, setName] = useState("");
  const [ownerName, setOwnerName] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const result = await api.createRoom({
        name,
        owner_name: ownerName.trim() || null,
        ends_at: endsAt ? new Date(endsAt).toISOString() : null,
        device_id: getDeviceId(),
      });
      saveSession({
        roomId: result.room.id,
        token: result.session_token,
        memberId: result.member.member_id,
        name: result.member.name,
        role: result.member.role,
      });
      onCreated(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't create the room.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Create a Room">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <Input
          label="Room name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          minLength={3}
          maxLength={40}
          placeholder="HackAlfred 2026"
          required
          autoFocus
        />
        <Input
          label="Your name (optional)"
          value={ownerName}
          onChange={(e) => setOwnerName(e.target.value)}
          maxLength={24}
          placeholder="Leave blank to stay anonymous"
        />
        <Input
          label="Ends at (optional)"
          type="datetime-local"
          value={endsAt}
          onChange={(e) => setEndsAt(e.target.value)}
        />
        {error && <p className="text-sm text-danger">{error}</p>}
        <Button type="submit" disabled={loading || name.trim().length < 3}>
          {loading ? "Creating…" : "Create Room"}
        </Button>
      </form>
    </Modal>
  );
}
