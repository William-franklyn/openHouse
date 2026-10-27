import { create } from "zustand";
import { CallSignalEvent, ChannelOut, MemberRole, MessageOut, PresenceMember, RoomPhoto } from "./types";

export interface IncomingCallInvite {
  callId: string;
  hostMemberId: string;
  hostName: string;
}

export type ConnectionStatus = "idle" | "connecting" | "open" | "reconnecting" | "closed";

export interface RoomMusicState {
  source: "upload" | "library";
  fileId?: string;
  url?: string;
  attribution?: string;
  filename: string;
  startedByMemberId: string;
  startedByName: string;
  startedAtMs: number;
}

interface RoomStoreState {
  status: ConnectionStatus;
  roomId: string | null;
  myMemberId: string | null;
  myRole: MemberRole | null;
  myName: string | null;
  channels: ChannelOut[];
  activeChannelId: string | null;
  messagesByChannel: Record<string, MessageOut[]>;
  lastSeqByChannel: Record<string, number>;
  online: PresenceMember[];
  pinnedIds: string[];
  ownershipOfferFrom: string | null;
  removedReason: string | null;
  roomDeletedMessage: string | null;
  roomEnded: boolean;
  lastError: { code: string; message: string } | null;
  music: RoomMusicState | null;
  // Every call_id this client currently knows about, keyed by call_id -
  // not a fixed "the call" slot, since multiple invite-based meetings can
  // be live in the same room at once.
  callPresenceByCallId: Record<string, string[]>;
  // The call_id I'm the host of or have accepted - null means no call
  // modal should be showing. Closing the modal clears this (and leaves).
  myCallId: string | null;
  // An unanswered invite to show as a popup - null once accepted/dismissed.
  incomingCallInvite: IncomingCallInvite | null;
  // Raw WebRTC signaling (offer/answer/ICE) - a queue, not an ephemeral
  // "last value" slot like everything else above: ICE candidates can
  // arrive in a rapid burst, and overwriting one with the next would
  // silently drop it instead of just showing a stale value.
  callSignalQueue: CallSignalEvent[];
  photos: RoomPhoto[];

  initRoom: (params: {
    roomId: string;
    memberId: string;
    role: MemberRole;
    name: string;
    channels: ChannelOut[];
  }) => void;
  setStatus: (status: ConnectionStatus) => void;
  setActiveChannel: (channelId: string) => void;
  prependHistory: (channelId: string, messages: MessageOut[]) => void;
  receiveMessage: (msg: MessageOut) => void;
  removeMessage: (channelId: string, messageId: string) => void;
  setPins: (ids: string[]) => void;
  setPresence: (online: PresenceMember[]) => void;
  addChannel: (channel: ChannelOut) => void;
  setMyRole: (role: MemberRole) => void;
  setOwnershipOffer: (fromName: string | null) => void;
  applyOwnershipChange: (newOwnerId: string) => void;
  setRemoved: (reason: string) => void;
  setRoomDeleted: (message: string) => void;
  setRoomEnded: () => void;
  setError: (code: string, message: string) => void;
  clearError: () => void;
  setMusic: (music: RoomMusicState | null) => void;
  setCallPresence: (callId: string, memberIds: string[]) => void;
  setMyCallId: (callId: string | null) => void;
  setIncomingCallInvite: (invite: IncomingCallInvite | null) => void;
  pushCallSignal: (event: CallSignalEvent) => void;
  clearCallSignals: () => void;
  addPhoto: (photo: RoomPhoto) => void;
  mergePhotos: (photos: RoomPhoto[]) => void;
  removePhotoByMessageId: (messageId: string) => void;
  reset: () => void;
}

const initialState = {
  status: "idle" as ConnectionStatus,
  roomId: null,
  myMemberId: null,
  myRole: null,
  myName: null,
  channels: [],
  activeChannelId: null,
  messagesByChannel: {},
  lastSeqByChannel: {},
  online: [],
  pinnedIds: [],
  ownershipOfferFrom: null,
  removedReason: null,
  roomDeletedMessage: null,
  roomEnded: false,
  lastError: null,
  music: null,
  callPresenceByCallId: {} as Record<string, string[]>,
  myCallId: null,
  incomingCallInvite: null,
  callSignalQueue: [],
  photos: [] as RoomPhoto[],
};

function bumpLastSeq(state: RoomStoreState, channelId: string, seq: number) {
  const current = state.lastSeqByChannel[channelId] ?? 0;
  if (seq > current) {
    return { ...state.lastSeqByChannel, [channelId]: seq };
  }
  return state.lastSeqByChannel;
}

export const useRoomStore = create<RoomStoreState>((set, get) => ({
  ...initialState,

  initRoom: ({ roomId, memberId, role, name, channels }) =>
    set({
      roomId,
      myMemberId: memberId,
      myRole: role,
      myName: name,
      channels,
      activeChannelId: channels[0]?.id ?? null,
    }),

  setStatus: (status) => set({ status }),

  setActiveChannel: (channelId) => set({ activeChannelId: channelId }),

  prependHistory: (channelId, messages) =>
    set((state) => {
      const existing = state.messagesByChannel[channelId] ?? [];
      const existingIds = new Set(existing.map((m) => m.id));
      const fresh = messages.filter((m) => !existingIds.has(m.id));
      return {
        messagesByChannel: {
          ...state.messagesByChannel,
          [channelId]: [...fresh, ...existing].sort((a, b) => a.seq - b.seq),
        },
      };
    }),

  receiveMessage: (msg) =>
    set((state) => {
      const existing = state.messagesByChannel[msg.channel_id] ?? [];
      if (existing.some((m) => m.id === msg.id)) {
        return {};
      }
      return {
        messagesByChannel: {
          ...state.messagesByChannel,
          [msg.channel_id]: [...existing, msg].sort((a, b) => a.seq - b.seq),
        },
        lastSeqByChannel: bumpLastSeq(state, msg.channel_id, msg.seq),
      };
    }),

  removeMessage: (channelId, messageId) =>
    set((state) => ({
      messagesByChannel: {
        ...state.messagesByChannel,
        [channelId]: (state.messagesByChannel[channelId] ?? []).filter((m) => m.id !== messageId),
      },
    })),

  setPins: (ids) => set({ pinnedIds: ids }),

  setPresence: (online) => set({ online }),

  addChannel: (channel) =>
    set((state) =>
      state.channels.some((c) => c.id === channel.id)
        ? {}
        : { channels: [...state.channels, channel] }
    ),

  setMyRole: (role) => set({ myRole: role }),

  setOwnershipOffer: (fromName) => set({ ownershipOfferFrom: fromName }),

  applyOwnershipChange: (newOwnerId) =>
    set((state) => ({
      myRole: state.myMemberId === newOwnerId ? "owner" : state.myRole === "owner" ? "member" : state.myRole,
      ownershipOfferFrom: null,
    })),

  setRemoved: (reason) => set({ removedReason: reason }),

  setRoomDeleted: (message) => set({ roomDeletedMessage: message }),

  setRoomEnded: () => set({ roomEnded: true }),

  setError: (code, message) => set({ lastError: { code, message } }),

  clearError: () => set({ lastError: null }),

  setMusic: (music) => set({ music }),

  setCallPresence: (callId, memberIds) =>
    set((state) => ({ callPresenceByCallId: { ...state.callPresenceByCallId, [callId]: memberIds } })),

  setMyCallId: (callId) => set({ myCallId: callId }),

  setIncomingCallInvite: (invite) => set({ incomingCallInvite: invite }),

  pushCallSignal: (event) =>
    set((state) => ({ callSignalQueue: [...state.callSignalQueue, event] })),

  clearCallSignals: () => set({ callSignalQueue: [] }),

  addPhoto: (photo) =>
    set((state) =>
      state.photos.some((p) => p.file_id === photo.file_id)
        ? {}
        : { photos: [...state.photos, photo] }
    ),

  mergePhotos: (photos) =>
    set((state) => {
      const existingIds = new Set(state.photos.map((p) => p.file_id));
      const fresh = photos.filter((p) => !existingIds.has(p.file_id));
      return {
        photos: [...state.photos, ...fresh].sort((a, b) => a.created_at.localeCompare(b.created_at)),
      };
    }),

  removePhotoByMessageId: (messageId) =>
    set((state) => ({ photos: state.photos.filter((p) => p.message_id !== messageId) })),

  reset: () => set(initialState),
}));

export function getLastSeqSnapshot(): Record<string, number> {
  return useRoomStore.getState().lastSeqByChannel;
}
