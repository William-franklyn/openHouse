"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Spinner } from "@/components/ui/Spinner";
import { api } from "@/lib/api";
import { getDeviceId } from "@/lib/device";
import { loadSession, saveSession, clearSession, StoredSession } from "@/lib/session";
import { ApiError, RoomPublic } from "@/lib/types";
import { WaitingForApproval } from "./WaitingForApproval";

export function JoinClient({ code, invitePrefill }: { code: string; invitePrefill: string | null }) {
  const router = useRouter();
  const [preview, setPreview] = useState<RoomPublic | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [existingSession, setExistingSession] = useState<StoredSession | null>(null);

  const [name, setName] = useState("");
  const [over18, setOver18] = useState(false);
  const [inviteCode, setInviteCode] = useState(invitePrefill ?? "");
  const [joinError, setJoinError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<"name" | "anon" | null>(null);
  const [pending, setPending] = useState<{ memberId: string; token: string } | null>(null);

  useEffect(() => {
    api
      .previewRoom(code)
      .then((room) => {
        setPreview(room);
        setExistingSession(loadSession(room.id));
      })
      .catch((err) => {
        setLoadError(err instanceof ApiError ? err.message : "That room code doesn't exist.");
      });
  }, [code]);

  async function submitJoin(anonymous: boolean) {
    if (!preview) return;
    setSubmitting(anonymous ? "anon" : "name");
    setJoinError(null);
    try {
      const result = await api.joinRoom(code, {
        name: anonymous ? null : name.trim() || null,
        over_18: over18,
        invite_code: preview.join_policy === "invite_only" ? inviteCode.trim() || null : null,
        device_id: getDeviceId(),
      });
      saveSession({
        roomId: result.room_id,
        token: result.session_token,
        memberId: result.member_id,
        name: anonymous ? "Guest" : name.trim() || "Guest",
        role: "member",
      });
      if (result.status === "pending") {
        setPending({ memberId: result.member_id, token: result.session_token });
      } else {
        router.push(`/room/${result.room_id}`);
      }
    } catch (err) {
      setJoinError(err instanceof ApiError ? err.message : "Couldn't join that room.");
    } finally {
      setSubmitting(null);
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    submitJoin(false);
  }

  if (pending) {
    return <WaitingForApproval roomId={preview!.id} memberId={pending.memberId} token={pending.token} />;
  }

  if (loadError) {
    return (
      <div className="mx-auto max-w-sm px-4 py-16 text-center">
        <h1 className="text-lg font-semibold">Can&apos;t join this room</h1>
        <p className="mt-2 text-sm text-danger">{loadError}</p>
        <Button variant="secondary" className="mt-6" onClick={() => router.push("/")}>
          Back home
        </Button>
      </div>
    );
  }

  if (!preview) {
    return (
      <div className="flex justify-center py-16">
        <Spinner className="h-6 w-6 text-accent" />
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-sm flex-col gap-6 px-4 py-10">
      <div className="text-center">
        <h1 className="text-xl font-semibold">{preview.name}</h1>
        <p className="mt-1 text-sm text-muted">
          {preview.member_count} {preview.member_count === 1 ? "person" : "people"} here now
        </p>
        <p className="mt-3 text-xs text-muted">
          Be respectful. Reports go to the room&apos;s house owner and moderators, and the platform team.
        </p>
        {preview.local_mode && (
          <p className="mt-3 text-xs text-accent">
            📶 This room is in Local mode right now — you&apos;ll need to be on the same Wi-Fi or
            hotspot as the host to join.
          </p>
        )}
      </div>

      {existingSession && (
        <div className="flex flex-col gap-2 rounded-xl border border-border bg-surface p-4">
          <Button onClick={() => router.push(`/room/${existingSession.roomId}`)}>
            Rejoin as {existingSession.name}
          </Button>
          <button
            type="button"
            onClick={() => {
              clearSession(existingSession.roomId);
              setExistingSession(null);
            }}
            className="text-xs text-muted underline"
          >
            Forget me
          </button>
        </div>
      )}

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <Input
          label="Name (optional)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={24}
          placeholder="Leave blank to stay anonymous"
        />

        {preview.join_policy === "invite_only" && (
          <Input
            label="Invite code"
            value={inviteCode}
            onChange={(e) => setInviteCode(e.target.value)}
            placeholder="Required for this room"
            required
          />
        )}

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={over18}
            onChange={(e) => setOver18(e.target.checked)}
            className="h-4 w-4"
          />
          I am 18 or older
        </label>

        {joinError && <p className="text-sm text-danger">{joinError}</p>}

        <Button type="submit" disabled={!over18 || submitting !== null}>
          {submitting === "name" ? "Joining…" : "Join"}
        </Button>
        <Button
          type="button"
          variant="secondary"
          disabled={!over18 || submitting !== null}
          onClick={() => submitJoin(true)}
        >
          {submitting === "anon" ? "Joining…" : "Join anonymously"}
        </Button>
      </form>
    </div>
  );
}
