"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Spinner } from "@/components/ui/Spinner";
import { useRoomSocket } from "@/lib/useRoomSocket";
import { useRoomStore } from "@/lib/store";

/** A pending member's session token already works for /ws (the backend
 * allows "pending" status to connect so it can wait for a live update) -
 * so "waiting for approval" is just: connect, and watch the store for
 * either a presence update that includes us (approved) or a `removed`
 * event (declined), reusing the same hook/store the chat screen uses. */
export function WaitingForApproval({
  roomId,
  memberId,
  token,
}: {
  roomId: string;
  memberId: string;
  token: string;
}) {
  const router = useRouter();
  useRoomSocket(token);
  const online = useRoomStore((s) => s.online);
  const removedReason = useRoomStore((s) => s.removedReason);

  useEffect(() => {
    if (online.some((m) => m.member_id === memberId)) {
      router.push(`/room/${roomId}`);
    }
  }, [online, memberId, roomId, router]);

  useEffect(() => {
    return () => useRoomStore.getState().reset();
  }, []);

  if (removedReason) {
    return (
      <div className="mx-auto max-w-sm px-4 py-16 text-center">
        <h1 className="text-lg font-semibold">Join request declined</h1>
        <p className="mt-2 text-sm text-muted">{removedReason}</p>
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-sm flex-col items-center gap-4 px-4 py-16 text-center">
      <Spinner className="h-8 w-8 text-accent" />
      <h1 className="text-lg font-semibold">Waiting for approval…</h1>
      <p className="text-sm text-muted">
        The room&apos;s house owner or a moderator needs to let you in. This page will move on
        automatically once they do.
      </p>
    </div>
  );
}
