import { MemberRole } from "./types";

const PREFIX = "openhouse_session_";

export interface StoredSession {
  roomId: string;
  token: string;
  memberId: string;
  name: string;
  role: MemberRole;
}

/** Session tokens live in localStorage keyed by room_id (matching how the
 * backend scopes them), wrapped in try/catch - some browsers (private
 * mode, disabled storage) throw on access rather than just no-op. */
export function saveSession(session: StoredSession): void {
  try {
    localStorage.setItem(PREFIX + session.roomId, JSON.stringify(session));
  } catch {
    // ignore
  }
}

export function loadSession(roomId: string): StoredSession | null {
  try {
    const raw = localStorage.getItem(PREFIX + roomId);
    if (!raw) return null;
    return JSON.parse(raw) as StoredSession;
  } catch {
    return null;
  }
}

export function clearSession(roomId: string): void {
  try {
    localStorage.removeItem(PREFIX + roomId);
  } catch {
    // ignore
  }
}
