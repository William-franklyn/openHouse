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

// ---- Video call: presence shared by both implementations, signaling
// used only by the self-hosted WebRTC one (Jitsi handles its own) ----

export type CallMode = "webrtc" | "jitsi";

export interface WSCallPresence {
  type: "call_presence";
  mode: CallMode;
  member_ids: string[];
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
  | WSCallOffer
  | WSCallAnswer
  | WSIceCandidate;

export class ApiError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}
