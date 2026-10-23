"use client";

import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { api } from "@/lib/api";
import { ApiError, JoinPolicy, RoomPublic } from "@/lib/types";
import { DeleteRoomDialog } from "./DeleteRoomDialog";

export function RoomSettingsPanel({
  open,
  onClose,
  roomId,
  token,
  room,
  onRoomUpdated,
  onDeleted,
}: {
  open: boolean;
  onClose: () => void;
  roomId: string;
  token: string;
  room: RoomPublic;
  onRoomUpdated: (room: RoomPublic) => void;
  onDeleted: () => void;
}) {
  const [joinPolicy, setJoinPolicy] = useState<JoinPolicy>(room.join_policy);
  const [inviteBy, setInviteBy] = useState<"admins" | "members">("admins");
  const [endsAt, setEndsAt] = useState("");
  const [newCode, setNewCode] = useState<string | null>(null);
  const [showDelete, setShowDelete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function savePolicy(policy: JoinPolicy) {
    setJoinPolicy(policy);
    setSaving(true);
    setError(null);
    try {
      const updated = await api.patchRoom(roomId, token, { join_policy: policy });
      onRoomUpdated(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't update the room.");
    } finally {
      setSaving(false);
    }
  }

  async function saveInviteBy(value: "admins" | "members") {
    setInviteBy(value);
    setSaving(true);
    try {
      await api.patchRoom(roomId, token, { invite_by: value });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't update the room.");
    } finally {
      setSaving(false);
    }
  }

  async function saveEndsAt() {
    setSaving(true);
    setError(null);
    try {
      const updated = await api.patchRoom(roomId, token, {
        ends_at: endsAt ? new Date(endsAt).toISOString() : null,
      });
      onRoomUpdated(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't update the room.");
    } finally {
      setSaving(false);
    }
  }

  async function rotateCode() {
    setSaving(true);
    setError(null);
    try {
      const result = await api.newCode(roomId, token);
      setNewCode(result.code);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't rotate the code.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    try {
      await api.deleteRoom(roomId, token);
      onDeleted();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't delete the room.");
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Room settings">
      <div className="flex flex-col gap-5">
        <Select
          label="Who can join"
          value={joinPolicy}
          onChange={(e) => savePolicy(e.target.value as JoinPolicy)}
          disabled={saving}
        >
          <option value="open">Open — anyone with the code</option>
          <option value="approval">Approval — house owner/mods approve each join</option>
          <option value="invite_only">Invite only — needs a one-time invite code</option>
        </Select>

        {joinPolicy === "invite_only" && (
          <Select
            label="Who can create invites"
            value={inviteBy}
            onChange={(e) => saveInviteBy(e.target.value as "admins" | "members")}
            disabled={saving}
          >
            <option value="admins">House owner + moderators only</option>
            <option value="members">Any member</option>
          </Select>
        )}

        <div>
          <label className="text-sm font-medium">Room code</label>
          <div className="mt-1.5 flex items-center gap-3">
            <span className="font-mono text-lg">{newCode ?? room.code}</span>
            <Button variant="secondary" size="sm" onClick={rotateCode} disabled={saving}>
              Generate new code
            </Button>
          </div>
          {newCode && <p className="mt-1 text-xs text-muted">The old code stopped working.</p>}
        </div>

        <div className="flex items-end gap-2">
          <Input
            label="Ends at"
            type="datetime-local"
            value={endsAt}
            onChange={(e) => setEndsAt(e.target.value)}
            className="flex-1"
          />
          <Button variant="secondary" size="sm" onClick={saveEndsAt} disabled={saving}>
            Save
          </Button>
        </div>

        <p className="text-xs text-muted">
          Make someone a moderator or hand over house owner from their name in the online list.
        </p>

        {error && <p className="text-sm text-danger">{error}</p>}

        <Button variant="danger" onClick={() => setShowDelete(true)}>
          Delete room
        </Button>
      </div>

      <DeleteRoomDialog
        open={showDelete}
        onClose={() => setShowDelete(false)}
        roomName={room.name}
        onConfirm={handleDelete}
      />
    </Modal>
  );
}
