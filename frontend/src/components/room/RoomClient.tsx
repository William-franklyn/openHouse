"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { api } from "@/lib/api";
import { clearSession, loadSession, StoredSession } from "@/lib/session";
import { useRoomStore } from "@/lib/store";
import { useRoomSocket } from "@/lib/useRoomSocket";
import { ApiError, RoomPublic } from "@/lib/types";
import { ChannelTabs } from "./ChannelTabs";
import { PinnedBanner } from "./PinnedBanner";
import { MessageList } from "./MessageList";
import { MessageInput } from "./MessageInput";
import { OnlineList } from "./OnlineList";
import { InviteModal } from "./InviteModal";
import { ReportModal } from "./ReportModal";
import { RoomSettingsPanel } from "./RoomSettingsPanel";
import { OwnershipOfferModal } from "./OwnershipOfferModal";
import { TerminalStateOverlay } from "./TerminalStateOverlay";

export function RoomClient({ roomId }: { roomId: string }) {
  const router = useRouter();
  const [session, setSession] = useState<StoredSession | null>(null);
  const [room, setRoom] = useState<RoomPublic | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showOnline, setShowOnline] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showInvite, setShowInvite] = useState(false);
  const [reportTarget, setReportTarget] = useState<{ memberId?: string; messageId?: string } | null>(null);

  const { send } = useRoomSocket(session?.token ?? null);

  const status = useRoomStore((s) => s.status);
  const activeChannelId = useRoomStore((s) => s.activeChannelId);
  const myRole = useRoomStore((s) => s.myRole);
  const ownershipOfferFrom = useRoomStore((s) => s.ownershipOfferFrom);
  const removedReason = useRoomStore((s) => s.removedReason);
  const roomDeletedMessage = useRoomStore((s) => s.roomDeletedMessage);
  const roomEnded = useRoomStore((s) => s.roomEnded);

  useEffect(() => {
    const stored = loadSession(roomId);
    if (!stored) {
      router.replace("/");
      return;
    }
    setSession(stored);

    api
      .getRoom(roomId, stored.token)
      .then((detail) => {
        setRoom(detail.room);
        useRoomStore.getState().initRoom({
          roomId: detail.room.id,
          memberId: detail.my_member_id,
          role: detail.my_role,
          name: stored.name,
          channels: detail.channels,
        });
      })
      .catch((err) => {
        setLoadError(err instanceof ApiError ? err.message : "Couldn't load this room.");
      });

    return () => useRoomStore.getState().reset();
  }, [roomId, router]);

  useEffect(() => {
    if (!session || !activeChannelId) return;
    if (useRoomStore.getState().messagesByChannel[activeChannelId]) return;
    api.history(roomId, activeChannelId, session.token).then((res) => {
      useRoomStore.getState().prependHistory(activeChannelId, res.messages);
    });
  }, [session, activeChannelId, roomId]);

  if (roomDeletedMessage) return <TerminalStateOverlay roomId={roomId} message={roomDeletedMessage} />;
  if (removedReason) return <TerminalStateOverlay roomId={roomId} message={removedReason} />;
  if (roomEnded) return <TerminalStateOverlay roomId={roomId} message="This room has ended." />;

  if (loadError) {
    return (
      <div className="mx-auto max-w-sm px-4 py-16 text-center">
        <h1 className="text-lg font-semibold">Can&apos;t open this room</h1>
        <p className="mt-2 text-sm text-danger">{loadError}</p>
        <Button
          variant="secondary"
          className="mt-6"
          onClick={() => {
            clearSession(roomId);
            router.push("/");
          }}
        >
          Back home
        </Button>
      </div>
    );
  }

  if (!session || !room || !activeChannelId) {
    return (
      <div className="flex justify-center py-16">
        <Spinner className="h-6 w-6 text-accent" />
      </div>
    );
  }

  const canInvite =
    myRole === "owner" ||
    myRole === "mod" ||
    (room.join_policy === "invite_only" && room.invite_by === "members");

  return (
    <div className="flex h-dvh flex-col">
      <header className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div>
          <h1 className="text-sm font-semibold">{room.name}</h1>
          <p className="text-xs text-muted">You are {session.name}</p>
        </div>
        <div className="flex items-center gap-2">
          {canInvite && (
            <Button variant="secondary" size="sm" onClick={() => setShowInvite(true)}>
              Invite
            </Button>
          )}
          {(myRole === "owner" || myRole === "mod") && (
            <Button variant="secondary" size="sm" onClick={() => setShowSettings(true)}>
              Settings
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            className="sm:hidden"
            onClick={() => setShowOnline((v) => !v)}
          >
            Online
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              send("leave");
              clearSession(roomId);
              router.push("/");
            }}
          >
            Log out
          </Button>
        </div>
      </header>

      <ChannelTabs onCreateChannel={(name) => send("create_channel", { name })} />
      <PinnedBanner />

      <div className="flex flex-1 overflow-hidden">
        <div className="flex flex-1 flex-col overflow-hidden">
          <MessageList
            roomId={roomId}
            channelId={activeChannelId}
            token={session.token}
            onPin={(messageId) => send("pin", { message_id: messageId })}
            onUnpin={(messageId) => send("unpin", { message_id: messageId })}
            onDeleteMessage={(messageId) => send("delete_message", { message_id: messageId })}
            onReportMessage={(messageId) => setReportTarget({ messageId })}
          />
          <MessageInput
            roomId={roomId}
            channelId={activeChannelId}
            token={session.token}
            onSend={(text) => send("send_message", { channel_id: activeChannelId, text })}
          />
          {status === "reconnecting" && (
            <p className="bg-surface-muted px-4 py-1 text-center text-xs text-muted">
              Disconnected — reconnecting…
            </p>
          )}
        </div>

        <div className={`${showOnline ? "fixed inset-0 z-40 bg-background sm:static sm:bg-transparent" : "hidden"} sm:block`}>
          <OnlineList
            onKick={(id) => send("remove_member", { member_id: id })}
            onBan={(id) => send("ban_member", { member_id: id })}
            onPromote={(id, role) => send("set_role", { member_id: id, role })}
            onOfferOwnership={(id) => send("offer_ownership", { member_id: id })}
            onReport={(id) => setReportTarget({ memberId: id })}
          />
        </div>
      </div>

      <InviteModal
        open={showInvite}
        onClose={() => setShowInvite(false)}
        roomId={roomId}
        roomCode={room.code}
        token={session.token}
      />
      <ReportModal
        open={reportTarget !== null}
        onClose={() => setReportTarget(null)}
        roomId={roomId}
        token={session.token}
        target={reportTarget}
      />
      {(myRole === "owner" || myRole === "mod") && (
        <RoomSettingsPanel
          open={showSettings}
          onClose={() => setShowSettings(false)}
          roomId={roomId}
          token={session.token}
          room={room}
          onRoomUpdated={setRoom}
          onDeleted={() => {
            clearSession(roomId);
            router.push("/");
          }}
        />
      )}
      <OwnershipOfferModal
        fromName={ownershipOfferFrom}
        onAnswer={(accept) => send("answer_ownership", { accept })}
      />
    </div>
  );
}
