import { MemberRole } from "./types";

// Display-only: the backend's role value stays "owner" (used throughout
// permission checks, the WS protocol, etc.) - this just controls what
// users actually see, so the room metaphor reads as "house owner"
// rather than the internal "owner"/"admin" the API talks about.
const LABELS: Record<MemberRole, string> = {
  owner: "House Owner",
  mod: "Mod",
  member: "Member",
};

export function roleLabel(role: MemberRole): string {
  return LABELS[role];
}
