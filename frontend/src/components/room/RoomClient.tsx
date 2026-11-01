"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { api } from "@/lib/api";
import { clearSession, loadSession, StoredSession } from "@/lib/session";
import { useRoomStore } from "@/lib/store";
import { useRoomSocket } from "@/lib/useRoomSocket";
import { ApiError, GameKind, PartyGameKind, RoomPublic } from "@/lib/types";
import { RoomSidebar } from "./RoomSidebar";
import { ConversationHeader } from "./ConversationHeader";
import { PinnedBanner } from "./PinnedBanner";
import { MessageList } from "./MessageList";
import { MessageInput } from "./MessageInput";
import { OnlineList } from "./OnlineList";
import { InviteModal } from "./InviteModal";
import { ReportModal } from "./ReportModal";
import { RoomSettingsPanel } from "./RoomSettingsPanel";
import { OwnershipOfferModal } from "./OwnershipOfferModal";
import { TerminalStateOverlay } from "./TerminalStateOverlay";
import { CreateChannelModal } from "./CreateChannelModal";
import { MusicPlayer } from "./MusicPlayer";
import { MusicPickerModal } from "./MusicPickerModal";
import { WebRTCCallModal } from "./WebRTCCallModal";
import { StartCallModal } from "./StartCallModal";
import { IncomingCallToast } from "./IncomingCallToast";
import { PhotoWallModal } from "./PhotoWallModal";
import { StartGameModal } from "./StartGameModal";
import { GamesModal } from "./GamesModal";
import { GameBoardModal } from "./GameBoardModal";
import { IncomingGameToast } from "./IncomingGameToast";
import { OutgoingChallengeToast } from "./OutgoingChallengeToast";
import { LiveGamesBanner } from "./LiveGamesBanner";
import { PartyGameModal } from "./PartyGameModal";
import { PartyGameBanner } from "./PartyGameBanner";

export function RoomClient({ roomId }: { roomId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const claimedPlayTokenRef = useRef<string | null>(null);
  const [session, setSession] = useState<StoredSession | null>(null);
  const [room, setRoom] = useState<RoomPublic | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showSidebar, setShowSidebar] = useState(false);
  const [showMembers, setShowMembers] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showInvite, setShowInvite] = useState(false);
  const [showCreateChannel, setShowCreateChannel] = useState(false);
  const [showMusicPicker, setShowMusicPicker] = useState(false);
  const [showStartCall, setShowStartCall] = useState(false);
  const [showPhotoWall, setShowPhotoWall] = useState(false);
  const [showGamesModal, setShowGamesModal] = useState(false);
  const [startGameKind, setStartGameKind] = useState<GameKind | null>(null);
  const [showGameBoard, setShowGameBoard] = useState(false);
  const [showPartyGameModal, setShowPartyGameModal] = useState(false);
  const [reportTarget, setReportTarget] = useState<{ memberId?: string; messageId?: string } | null>(null);

  const { send } = useRoomSocket(session?.token ?? null);

  const status = useRoomStore((s) => s.status);
  const activeChannelId = useRoomStore((s) => s.activeChannelId);
  const myRole = useRoomStore((s) => s.myRole);
  const myMemberId = useRoomStore((s) => s.myMemberId);
  const myCallId = useRoomStore((s) => s.myCallId);
  const myGameId = useRoomStore((s) => s.myGameId);
  const linkWaitingGame = useRoomStore((s) => s.linkWaitingGame);
  const myPartyGame = useRoomStore((s) => s.myPartyGame);
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

  // Members panel open by default on large screens, closed on small ones.
  useEffect(() => {
    if (typeof window === "undefined") return;
    setShowMembers(window.matchMedia("(min-width: 1280px)").matches);
  }, []);

  // A new game_id (challenge just accepted, or a reconnect snapshot found
  // one already active) pops the board open for both players - closing it
  // afterward only hides it (myGameId itself isn't cleared), so it doesn't
  // reopen on its own again until the next genuinely new game. A fresh
  // invite link you just generated does the same.
  useEffect(() => {
    if (myGameId || linkWaitingGame) setShowGameBoard(true);
  }, [myGameId, linkWaitingGame]);

  // Same auto-open idea as the board-game effect above, but gated on
  // actually being a participant - a party game is room-wide, so
  // everyone gets the party_state broadcast while it's in "lobby", and
  // only joiners (not every bystander in the room) should have their
  // screen taken over by the modal. Non-participants instead see
  // PartyGameBanner, a much lighter nudge.
  useEffect(() => {
    if (myPartyGame && myMemberId && myPartyGame.participantIds.includes(myMemberId)) {
      setShowPartyGameModal(true);
    }
  }, [myPartyGame, myMemberId]);

  // A ?play=<token> in the URL (from an invite link) gets claimed once the
  // socket is open, then stripped from the URL so a refresh doesn't
  // re-send it. Guarded by a ref, not just the query param itself, since
  // the param can briefly still be present across a reconnect.
  useEffect(() => {
    const token = searchParams.get("play");
    if (!token || status !== "open" || claimedPlayTokenRef.current === token) return;
    claimedPlayTokenRef.current = token;
    send("claim_game_link", { token });
    router.replace(`/room/${roomId}`);
  }, [searchParams, status, send, router, roomId]);

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
      <div className="flex h-dvh items-center justify-center">
        <Spinner className="h-6 w-6 text-accent" />
      </div>
    );
  }

  const canInvite =
    myRole === "owner" ||
    myRole === "mod" ||
    (room.join_policy === "invite_only" && room.invite_by === "members");
  const canManage = myRole === "owner" || myRole === "mod";

  function handleLogout() {
    send("leave");
    clearSession(roomId);
    router.push("/");
  }

  return (
    <div className="flex h-dvh overflow-hidden bg-background">
      <RoomSidebar
        roomName={room.name}
        myName={session.name}
        myRole={myRole}
        canInvite={canInvite}
        canManage={canManage}
        mobileOpen={showSidebar}
        onCloseMobile={() => setShowSidebar(false)}
        onOpenCreateChannel={() => setShowCreateChannel(true)}
        onInvite={() => setShowInvite(true)}
        onSettings={() => setShowSettings(true)}
        onLogout={handleLogout}
      />

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <ConversationHeader
          onOpenSidebar={() => setShowSidebar(true)}
          onToggleMembers={() => setShowMembers((v) => !v)}
          membersOpen={showMembers}
          onOpenStartCall={() => setShowStartCall(true)}
          onOpenPhotoWall={() => setShowPhotoWall(true)}
          onOpenGames={() =>
            myGameId
              ? setShowGameBoard(true)
              : myPartyGame && myMemberId && myPartyGame.participantIds.includes(myMemberId)
                ? setShowPartyGameModal(true)
                : setShowGamesModal(true)
          }
          onOpenMusicPicker={() => setShowMusicPicker(true)}
        />
        <LiveGamesBanner send={send} />
        {myMemberId && <PartyGameBanner myMemberId={myMemberId} send={send} />}
        <PinnedBanner />
        <MusicPlayer
          token={session.token}
          onStop={() => send("stop_music")}
          onTrackEnded={(trackId) => send("music_track_ended", { track_id: trackId })}
          onCancelQueued={(trackId) => send("cancel_queued_music", { track_id: trackId })}
        />

        <div className="flex min-h-0 flex-1 overflow-hidden">
          <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
            <MessageList
              roomId={roomId}
              channelId={activeChannelId}
              token={session.token}
              onPin={(messageId) => send("pin", { message_id: messageId })}
              onUnpin={(messageId) => send("unpin", { message_id: messageId })}
              onDeleteMessage={(messageId) => send("delete_message", { message_id: messageId })}
              onReportMessage={(messageId) => setReportTarget({ messageId })}
            />
            {status === "reconnecting" && (
              <p className="bg-accent-soft px-4 py-1.5 text-center text-[12px] font-medium text-accent">
                Disconnected — reconnecting…
              </p>
            )}
            <MessageInput
              roomId={roomId}
              channelId={activeChannelId}
              token={session.token}
              onSend={(text) => send("send_message", { channel_id: activeChannelId, text })}
            />
          </div>

          <OnlineList
            open={showMembers}
            onClose={() => setShowMembers(false)}
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
      {canManage && (
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
      <CreateChannelModal
        open={showCreateChannel}
        onClose={() => setShowCreateChannel(false)}
        onCreate={(name) => {
          send("create_channel", { name });
          setShowCreateChannel(false);
        }}
      />
      <MusicPickerModal
        open={showMusicPicker}
        onClose={() => setShowMusicPicker(false)}
        roomId={roomId}
        token={session.token}
        onPicked={(pick) => send("start_music", pick)}
      />
      {myMemberId && (
        <StartCallModal
          open={showStartCall}
          onClose={() => setShowStartCall(false)}
          myMemberId={myMemberId}
          onStart={(inviteeIds) => send("start_call", { invitee_ids: inviteeIds })}
        />
      )}
      {myMemberId && myCallId && (
        <WebRTCCallModal
          open
          onClose={() => useRoomStore.getState().setMyCallId(null)}
          callId={myCallId}
          myMemberId={myMemberId}
          myName={session.name}
          token={session.token}
          send={send}
        />
      )}
      <IncomingCallToast />
      <PhotoWallModal
        open={showPhotoWall}
        onClose={() => setShowPhotoWall(false)}
        roomId={roomId}
        token={session.token}
      />
      <GamesModal
        open={showGamesModal}
        onClose={() => setShowGamesModal(false)}
        onPick={(kind) => setStartGameKind(kind)}
        onPickParty={(kind: PartyGameKind) => send("start_party_game", { kind })}
      />
      {myMemberId && startGameKind && (
        <StartGameModal
          open
          kind={startGameKind}
          onClose={() => setStartGameKind(null)}
          myMemberId={myMemberId}
          onChallenge={(opponentId) => send("challenge_game", { opponent_id: opponentId, kind: startGameKind })}
          onInviteLink={() => send("create_game_link", { kind: startGameKind })}
        />
      )}
      {myMemberId && (
        <GameBoardModal
          open={showGameBoard}
          onClose={() => setShowGameBoard(false)}
          myMemberId={myMemberId}
          myName={session.name}
          roomId={roomId}
          roomCode={room.code}
          token={session.token}
          send={send}
        />
      )}
      {myMemberId && (
        <PartyGameModal
          open={showPartyGameModal}
          onClose={() => setShowPartyGameModal(false)}
          myMemberId={myMemberId}
          send={send}
        />
      )}
      <IncomingGameToast send={send} />
      <OutgoingChallengeToast send={send} />
    </div>
  );
}
