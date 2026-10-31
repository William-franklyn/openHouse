// Mirrors the backend's response shapes exactly (see backend/app/main.py).

export type JoinPolicy = "open" | "approval" | "invite_only";
export type InviteBy = "admins" | "members";
export type MemberRole = "owner" | "mod" | "member";
export type MemberStatus = "pending" | "active" | "left" | "removed" | "banned";

export interface RoomPublic {
  id: string;
  name: string;
  code: string;
  member_count: number;
  join_policy: JoinPolicy;
  invite_by: InviteBy | null;
  is_active: boolean;
  // True if the owner restricted joining to people on their current
  // Wi-Fi/hotspot (see RoomSettingsPanel). Never carries the actual IP.
  local_mode: boolean;
}

export interface MemberOut {
  member_id: string;
  name: string;
  is_anonymous: boolean;
  role: MemberRole;
  status: MemberStatus;
}

export interface ChannelOut {
  id: string;
  name: string;
}

export interface MessageOut {
  id: string;
  channel_id: string;
  seq: number;
  member_id: string | null;
  from_name: string | null;
  kind: "text" | "file" | "system";
  text: string | null;
  file_id: string | null;
  created_at: string;
}

export interface CreateRoomResponse {
  room: RoomPublic;
  member: MemberOut;
  session_token: string;
  recovery_code: string;
}

export interface JoinResponse {
  member_id: string;
  room_id: string;
  session_token: string;
  status: MemberStatus;
}

export interface RecoverResponse {
  member: MemberOut;
  session_token: string;
}

export interface RoomDetail {
  room: RoomPublic;
  my_role: MemberRole;
  my_member_id: string;
  channels: ChannelOut[];
  video_room_token: string;
}

export interface InviteCreated {
  code: string;
  expires_at: string;
}

export interface HistoryResponse {
  messages: MessageOut[];
}

export interface UploadResponse {
  file_id: string;
  filename: string;
  size: number;
}

export interface DownloadResponse {
  url: string;
  filename: string;
  size: number;
  expires_in: number;
}

export interface ReportResponse {
  report_id: string;
  status: "open" | "done";
}

export interface AdminReport {
  id: string;
  room_id: string;
  reporter_member_id: string;
  target_member_id: string | null;
  message_id: string | null;
  reason: string;
  status: "open" | "done";
  created_at: string;
}

export interface AdminMetricRow {
  day: string;
  name: string;
  value: number;
}

// ---- WebSocket event payloads (server -> client) ----

export interface WSReady {
  type: "ready";
}

export interface WSMessage {
  type: "message";
  channel_id: string;
  id: string;
  seq: number;
  member_id: string | null;
  from_name: string | null;
  kind: "text" | "file" | "system";
  text: string | null;
  file_id: string | null;
  client_id: string | null;
  created_at: string;
}

export interface WSMessageDeleted {
  type: "message_deleted";
  channel_id: string;
  message_id: string;
}

export interface WSPins {
  type: "pins";
  message_ids: string[];
}

export interface PresenceMember {
  member_id: string;
  name: string;
  role: MemberRole;
}

export interface WSPresence {
  type: "presence";
  online: PresenceMember[];
}

export interface WSMemberJoined {
  type: "member_joined";
  member_id: string;
  name: string;
}

export interface WSMemberLeft {
  type: "member_left";
  member_id: string;
}

export interface WSRoleChanged {
  type: "role_changed";
  member_id: string;
  role: MemberRole;
}

export interface WSOwnershipOffer {
  type: "ownership_offer";
  from_name: string;
}

export interface WSOwnershipChanged {
  type: "ownership_changed";
  new_owner_id: string;
  message: string;
}

export interface WSChannelCreated {
  type: "channel_created";
  channel_id: string;
  name: string;
}

export interface WSRemoved {
  type: "removed";
  reason: string;
}

export interface WSRoomDeleted {
  type: "room_deleted";
  message: string;
}

export interface WSRoomEnded {
  type: "room_ended";
  message?: string;
}

export interface WSError {
  type: "error";
  code: string;
  message: string;
}

export interface WSMusicStarted {
  type: "music_started";
  source: "upload" | "library";
  file_id?: string;
  url?: string;
  attribution?: string;
  filename: string;
  started_by_member_id: string;
  started_by_name: string;
  started_at_ms: number;
}

export interface WSMusicStopped {
  type: "music_stopped";
}

export interface MusicLibraryTrack {
  id: string;
  title: string;
  artist: string;
  license: string;
  license_url: string;
  url: string;
}

export interface MusicLibraryResponse {
  tracks: MusicLibraryTrack[];
}

// ---- Video call: self-hosted WebRTC only. A "call" is an invite-based
// meeting identified by call_id, not an ambient room-wide thing - two
// members separately clicking a generic "join" button had no guarantee
// they'd land in the same meeting, which is exactly what call_id fixes. ----

export interface IceServersResponse {
  iceServers: RTCIceServer[];
}

export interface WSCallPresence {
  type: "call_presence";
  call_id: string;
  member_ids: string[];
}

export interface WSCallInvite {
  type: "call_invite";
  call_id: string;
  host_member_id: string;
  host_name: string;
}

export interface WSCallOffer {
  type: "call_offer";
  from_member_id: string;
  sdp: RTCSessionDescriptionInit;
}

export interface WSCallAnswer {
  type: "call_answer";
  from_member_id: string;
  sdp: RTCSessionDescriptionInit;
}

export interface WSIceCandidate {
  type: "ice_candidate";
  from_member_id: string;
  candidate: RTCIceCandidateInit;
}

export type CallSignalEvent = WSCallOffer | WSCallAnswer | WSIceCandidate;

// ---- Photo Wall: every image shared as a chat message, room-wide ----

export interface RoomPhoto {
  file_id: string;
  message_id: string;
  filename: string;
  member_id: string | null;
  member_name: string | null;
  created_at: string;
}

export interface RoomPhotosResponse {
  photos: RoomPhoto[];
}

export interface WSPhotoShared {
  type: "photo_shared";
  file_id: string;
  message_id: string;
  filename: string;
  member_id: string;
  member_name: string;
  created_at: string;
}

// ---- Games: chess is the first. One pending-or-active game per member
// per room at a time (enforced server-side) - the frontend only ever
// needs a single myGameId slot, same shape as myCallId. ----

export type GameKind = "chess";
export type GameStatus = "pending" | "active" | "finished";
export type GameResult = "white" | "black" | "draw";

export interface WSGameInvite {
  type: "game_invite";
  game_id: string;
  kind: GameKind;
  challenger_member_id: string;
  challenger_name: string;
  opponent_member_id: string;
  opponent_name: string;
}

export interface WSGameDeclined {
  type: "game_declined";
  game_id: string;
}

export interface WSGameCancelled {
  type: "game_cancelled";
  game_id: string;
}

export interface WSGameState {
  type: "game_state";
  game_id: string;
  kind: GameKind;
  status: GameStatus;
  white_member_id: string;
  white_name: string;
  black_member_id: string;
  black_name: string;
  moves: string[];
  board_fen: string;
  turn: "white" | "black";
  legal_moves: string[];
  in_check: boolean;
  game_over: boolean;
  result: GameResult | null;
  termination: string | null;
  last_move: string | null;
}

export type WSServerEvent =
  | WSReady
  | WSMessage
  | WSMessageDeleted
  | WSPins
  | WSPresence
  | WSMemberJoined
  | WSMemberLeft
  | WSRoleChanged
  | WSOwnershipOffer
  | WSOwnershipChanged
  | WSChannelCreated
  | WSRemoved
  | WSRoomDeleted
  | WSRoomEnded
  | WSError
  | WSMusicStarted
  | WSMusicStopped
  | WSCallPresence
  | WSCallInvite
  | WSCallOffer
  | WSCallAnswer
  | WSIceCandidate
  | WSPhotoShared
  | WSGameInvite
  | WSGameDeclined
  | WSGameCancelled
  | WSGameState;

export class ApiError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}
