const KEY = "openhouse_blocked_members";

/** "Block a member: you no longer see their messages (on your device
 * only)" - purely client-side by design, no backend endpoint for it. */
export function getBlockedIds(): Set<string> {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch {
    return new Set();
  }
}

export function blockMember(memberId: string): Set<string> {
  const ids = getBlockedIds();
  ids.add(memberId);
  try {
    localStorage.setItem(KEY, JSON.stringify([...ids]));
  } catch {
    // ignore
  }
  return ids;
}

export function unblockMember(memberId: string): Set<string> {
  const ids = getBlockedIds();
  ids.delete(memberId);
  try {
    localStorage.setItem(KEY, JSON.stringify([...ids]));
  } catch {
    // ignore
  }
  return ids;
}
