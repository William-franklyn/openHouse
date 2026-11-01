import { create } from "zustand";
import {
  BattleshipCell,
  CallSignalEvent,
  CardGameKind,
  CardGameStatus,
  ChannelOut,
  GameKind,
  GameResult,
  GameStatus,
  MemberRole,
  MessageOut,
  PartyGameKind,
  PartyGameStatus,
  PartyRoundPhase,
  PartyScoreRow,
  PokerActionKind,
  PokerPhase,
  PresenceMember,
  RoomPhoto,
  TriviaQuestionPublic,
  TriviaQuestionRevealed,
} from "./types";

export interface IncomingCallInvite {
  callId: string;
  hostMemberId: string;
  hostName: string;
}

export interface IncomingGameInvite {
  gameId: string;
  kind: GameKind;
  challengerMemberId: string;
  challengerName: string;
}

interface GameStateBase {
  gameId: string;
  status: GameStatus;
  whiteMemberId: string;
  whiteName: string;
  blackMemberId: string;
  blackName: string;
  moves: unknown[];
  turn: "white" | "black";
  gameOver: boolean;
  result: GameResult | null;
  termination: string | null;
  lastMove: unknown | null;
}

export interface ChessGameState extends GameStateBase {
  kind: "chess";
  boardFen: string;
  legalMoves: string[];
  inCheck: boolean;
  lastMoveWasCapture: boolean;
}

export interface TicTacToeGameState extends GameStateBase {
  kind: "tictactoe";
  board: (0 | 1 | null)[];
}

export interface Connect4GameState extends GameStateBase {
  kind: "connect4";
  board: (0 | 1 | null)[][];
  legalMoves: { column: number }[];
}

export interface DotsAndBoxesGameState extends GameStateBase {
  kind: "dots_and_boxes";
  hEdges: boolean[][];
  vEdges: boolean[][];
  boxes: (0 | 1 | null)[][];
}

export interface ReversiGameState extends GameStateBase {
  kind: "reversi";
  board: (0 | 1 | null)[][];
  legalMoves: { row: number; col: number }[];
}

export interface CheckersGameState extends GameStateBase {
  kind: "checkers";
  board: (string | null)[][];
  mustContinueFrom: [number, number] | null;
  legalMoves: { from: [number, number]; to: [number, number] }[];
}

export interface BackgammonGameState extends GameStateBase {
  kind: "backgammon";
  points: number[];
  bar: [number, number];
  borneOff: [number, number];
  dice: number[];
  remainingDice: number[];
  legalMoves: { from: number; to: number }[];
}

export interface BattleshipGameState extends GameStateBase {
  kind: "battleship";
  whiteGrid: BattleshipCell[][];
  blackGrid: BattleshipCell[][];
  shipHits: [number[], number[]];
  shipSizes: number[];
}

export type GameState =
  | ChessGameState
  | TicTacToeGameState
  | Connect4GameState
  | DotsAndBoxesGameState
  | ReversiGameState
  | CheckersGameState
  | BackgammonGameState
  | BattleshipGameState;

// A room-wide "live now" banner entry - lighter than GameState (no board),
// for games this member isn't playing in. Clicking one sends watch_game,
// which fetches the real GameState for read-only viewing.
export interface LiveGame {
  gameId: string;
  kind: GameKind;
  whiteMemberId: string;
  whiteName: string;
  blackMemberId: string;
  blackName: string;
}

// Party games (trivia, the first) - N arbitrary participants, not 2
// seats, so this is a genuinely separate state shape from GameState, not
// another member of its union. One live party game per ROOM at a time
// (not per-member like board games), so a single nullable slot is enough
// - no Record<id, ...> the way callPresenceByCallId needs for calls.
export interface PartyGameState {
  partyGameId: string;
  kind: PartyGameKind;
  status: PartyGameStatus;
  hostMemberId: string;
  roundIndex: number;
  totalRounds: number;
  participantIds: string[];
  scoreboard: PartyScoreRow[];
  phase: PartyRoundPhase;
  question: TriviaQuestionPublic | TriviaQuestionRevealed | null;
  roundStartedAtMs: number | null;
  roundDeadlineMs: number | null;
  answeredMemberIds: string[];
  myAnswer: { choiceIndex: number } | null;
  answers: Record<string, { choiceIndex: number; answeredAtMs: number }> | null;
  roundPointsAwarded: Record<string, number> | null;
}

// Card games (poker, the first) - a seated table whose chip stacks
// persist across many hands, a third shape distinct from both GameState
// (2 seats) and PartyGameState (one round, synchronized reveal). One
// live card game per room, same single-slot reasoning as myPartyGame.
export interface CardLobbySeat {
  memberId: string;
  name: string;
}

export interface CardActiveSeat {
  memberId: string;
  name: string;
  chips: number;
  betThisStreet: number;
  folded: boolean;
  allIn: boolean;
  sittingOut: boolean;
  holeCards: [string, string] | null;
  handDescription: string | null;
}

interface CardGameStateBase {
  cardGameId: string;
  kind: CardGameKind;
  status: CardGameStatus;
  hostMemberId: string;
  participantIds: string[];
  startingChips: number;
}

export interface CardLobbyState extends CardGameStateBase {
  phase: "lobby";
  seats: CardLobbySeat[];
}

export interface CardActiveState extends CardGameStateBase {
  phase: Exclude<PokerPhase, "lobby">;
  handNumber: number;
  dealerIndex: number;
  smallBlind: number;
  bigBlind: number;
  communityCards: string[];
  pot: number;
  currentBet: number;
  actionOn: string | null;
  seats: CardActiveSeat[];
  myLegalActions: {
    actions: PokerActionKind[];
    callAmount: number;
    minRaiseTo: number | null;
    maxRaiseTo: number | null;
  };
  potSummary: { amount: number; winners: string[]; eligible: string[] }[] | null;
}

export type CardGameState = CardLobbyState | CardActiveState;

export type ConnectionStatus = "idle" | "connecting" | "open" | "reconnecting" | "closed";

export interface RoomMusicState {
  id: string;
  source: "upload" | "library";
  fileId?: string;
  url?: string;
  attribution?: string;
  filename: string;
  startedByMemberId: string;
  startedByName: string;
  startedAtMs: number;
}

export interface QueuedMusicTrack {
  id: string;
  source: "upload" | "library";
  fileId?: string;
  url?: string;
  attribution?: string;
  filename: string;
  requestedByMemberId: string;
  requestedByName: string;
  queuedAtMs: number;
}

export interface MusicRequestNotice {
  filename: string;
  requestedByName: string;
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
  musicQueue: QueuedMusicTrack[];
  musicRequestNotice: MusicRequestNotice | null;
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

  // An unanswered challenge TO me - a toast with accept/decline, same role
  // as incomingCallInvite.
  incomingGameInvite: IncomingGameInvite | null;
  // A challenge I sent that's still awaiting a reply - shown as a small
  // "waiting for X" state instead of a toast, since I'm the one who acted.
  pendingChallenge: { gameId: string; kind: GameKind; opponentName: string } | null;
  // The one active game's board - null means no board modal should show.
  // Closing the modal just hides it (setMyGameId(null)); the game itself
  // lives server-side (Postgres), so it's not lost, only reconnect/reopen
  // needs to resync, same as myCallId does for video calls.
  myGameId: string | null;
  game: GameState | null;

  // Every currently-live game in the room that I'm NOT playing in, keyed
  // by game_id - the non-interrupting room-wide "X vs Y is live" banner.
  liveGames: Record<string, LiveGame>;
  // Spectating is tracked separately from my own game (myGameId/game) -
  // you can watch a game that isn't yours, even while not playing one of
  // your own, and the two must never collide in the same slot.
  watchingGameId: string | null;
  watchedGame: GameState | null;
  // Spectator counts, keyed by game_id - decoupled from liveGames since
  // it's needed for my own game too (excluded from liveGames on purpose),
  // not just games I might watch.
  watcherCounts: Record<string, number>;
  // A link-challenge I created, awaiting someone to claim it - cleared
  // the moment a real game_state for the same game_id arrives (claimed)
  // or it's cancelled. Separate from pendingChallenge (that's a targeted
  // invite to someone already present, not a shareable link).
  linkWaitingGame: { gameId: string; kind: GameKind; linkToken: string } | null;

  // The one live party game in this room, if any - null means no party
  // game overlay should show. Room-wide, not per-member (unlike
  // myGameId): everyone in the room sees the same slot.
  myPartyGame: PartyGameState | null;

  // The one live card game (poker table) in this room, if any - same
  // room-wide single-slot shape as myPartyGame.
  myCardGame: CardGameState | null;

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
  setMusicQueue: (queue: QueuedMusicTrack[]) => void;
  setMusicRequestNotice: (notice: MusicRequestNotice | null) => void;
  setCallPresence: (callId: string, memberIds: string[]) => void;
  setMyCallId: (callId: string | null) => void;
  setIncomingCallInvite: (invite: IncomingCallInvite | null) => void;
  pushCallSignal: (event: CallSignalEvent) => void;
  clearCallSignals: () => void;
  addPhoto: (photo: RoomPhoto) => void;
  mergePhotos: (photos: RoomPhoto[]) => void;
  removePhotoByMessageId: (messageId: string) => void;
  setIncomingGameInvite: (invite: IncomingGameInvite | null) => void;
  setPendingChallenge: (challenge: { gameId: string; kind: GameKind; opponentName: string } | null) => void;
  setMyGameId: (gameId: string | null) => void;
  setGame: (game: GameState | null) => void;
  setLiveGame: (game: LiveGame) => void;
  removeLiveGame: (gameId: string) => void;
  setWatcherCount: (gameId: string, count: number) => void;
  setWatchingGameId: (gameId: string | null) => void;
  setWatchedGame: (game: GameState | null) => void;
  setLinkWaitingGame: (game: { gameId: string; kind: GameKind; linkToken: string } | null) => void;
  setPartyGame: (game: PartyGameState | null) => void;
  setCardGame: (game: CardGameState | null) => void;
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
  musicQueue: [],
  musicRequestNotice: null,
  callPresenceByCallId: {} as Record<string, string[]>,
  myCallId: null,
  incomingCallInvite: null,
  callSignalQueue: [],
  photos: [] as RoomPhoto[],
  incomingGameInvite: null as IncomingGameInvite | null,
  pendingChallenge: null as { gameId: string; kind: GameKind; opponentName: string } | null,
  myGameId: null as string | null,
  game: null as GameState | null,
  liveGames: {} as Record<string, LiveGame>,
  watchingGameId: null as string | null,
  watchedGame: null as GameState | null,
  watcherCounts: {} as Record<string, number>,
  linkWaitingGame: null as { gameId: string; kind: GameKind; linkToken: string } | null,
  myPartyGame: null as PartyGameState | null,
  myCardGame: null as CardGameState | null,
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
  setMusicQueue: (musicQueue) => set({ musicQueue }),
  setMusicRequestNotice: (musicRequestNotice) => set({ musicRequestNotice }),

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

  setIncomingGameInvite: (invite) => set({ incomingGameInvite: invite }),

  setPendingChallenge: (challenge) => set({ pendingChallenge: challenge }),

  setMyGameId: (gameId) => set({ myGameId: gameId }),

  setGame: (game) => set({ game }),

  setLiveGame: (game) =>
    set((state) => ({ liveGames: { ...state.liveGames, [game.gameId]: game } })),

  removeLiveGame: (gameId) =>
    set((state) => {
      if (!(gameId in state.liveGames)) return {};
      const next = { ...state.liveGames };
      delete next[gameId];
      return { liveGames: next };
    }),

  setWatcherCount: (gameId, count) =>
    set((state) => ({ watcherCounts: { ...state.watcherCounts, [gameId]: count } })),

  setWatchingGameId: (gameId) => set({ watchingGameId: gameId }),

  setWatchedGame: (game) => set({ watchedGame: game }),

  setLinkWaitingGame: (game) => set({ linkWaitingGame: game }),

  setPartyGame: (game) => set({ myPartyGame: game }),

  setCardGame: (game) => set({ myCardGame: game }),

  reset: () => set(initialState),
}));

export function getLastSeqSnapshot(): Record<string, number> {
  return useRoomStore.getState().lastSeqByChannel;
}
