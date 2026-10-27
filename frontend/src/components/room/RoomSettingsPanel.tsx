"use client";

import { useState } from "react";
import { DoorClosed, Trash2 } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { api } from "@/lib/api";
import { useRoomStore } from "@/lib/store";
import { ApiError, JoinPolicy, RoomPublic } from "@/lib/types";
import { DeleteRoomDialog } from "./DeleteRoomDialog";
import { EndRoomDialog } from "./EndRoomDialog";

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
  const myRole = useRoomStore((s) => s.myRole);
  const [joinPolicy, setJoinPolicy] = useState<JoinPolicy>(room.join_policy);
  const [inviteBy, setInviteBy] = useState<"admins" | "members">("admins");
  const [endsAt, setEndsAt] = useState("");
  const [newCode, setNewCode] = useState<string | null>(null);
  const [localMode, setLocalMode] = useState(room.local_mode);
  const [togglingLocalMode, setTogglingLocalMode] = useState(false);
  const [showEnd, setShowEnd] = useState(false);
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

  async function toggleLocalMode() {
    const next = !localMode;
    setTogglingLocalMode(true);
    setError(null);
    try {
      const updated = await api.setLocalMode(roomId, token, next);
      setLocalMode(updated.local_mode);
      onRoomUpdated(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't update Local mode.");
    } finally {
      setTogglingLocalMode(false);
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

  async function handleEnd() {
    try {
      await api.endRoom(roomId, token);
      // No further state update here - the room-wide "room_ended" broadcast
      // this triggers arrives over the same WS connection RoomClient already
      // listens on, which is what actually swaps in the terminal overlay.
      setShowEnd(false);
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't end the room.");
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

        <div className="rounded-[var(--radius-md)] border border-border bg-surface-muted p-3.5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium">Local mode</p>
              <p className="mt-0.5 text-xs text-muted">
                {localMode
                  ? "On — only people on this same Wi-Fi/hotspot can join right now."
                  : "Restrict joining to people on one Wi-Fi network or hotspot, right now."}
              </p>
            </div>
            <Button
              variant={localMode ? "danger" : "secondary"}
              size="sm"
              onClick={toggleLocalMode}
              disabled={togglingLocalMode}
            >
              {localMode ? "Turn off" : "Turn on"}
            </Button>
          </div>
          {!localMode && (
            <p className="mt-2 text-xs text-muted">
              Turn this on from the Wi-Fi or hotspot you want to allow — people elsewhere on the
              code won&apos;t be able to join until you turn it off. Doesn&apos;t use anyone&apos;s
              location, just whether they&apos;re on the same network.
            </p>
          )}
        </div>

        <div>
          <label className="text-sm font-medium">Room code</label>
          <div className="mt-1.5 flex items-center justify-between gap-3 rounded-[var(--radius-md)] border border-border bg-surface-muted px-3.5 py-2.5">
            <span className="font-mono text-[16px] font-semibold tracking-wide">{newCode ?? room.code}</span>
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

        {myRole === "owner" ? (
          <>
            <Button variant="secondary" onClick={() => setShowEnd(true)}>
              <DoorClosed size={15} />
              End room now
            </Button>

            <Button variant="danger" onClick={() => setShowDelete(true)}>
              <Trash2 size={15} />
              Delete room
            </Button>
          </>
        ) : (
          <p className="text-xs text-muted">
            Only the house owner can end or delete the room.
          </p>
        )}
      </div>

      <EndRoomDialog open={showEnd} onClose={() => setShowEnd(false)} onConfirm={handleEnd} />
      <DeleteRoomDialog
        open={showDelete}
        onClose={() => setShowDelete(false)}
        roomName={room.name}
        onConfirm={handleDelete}
      />
    </Modal>
  );
}
