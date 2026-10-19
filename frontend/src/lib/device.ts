const DEVICE_KEY = "openhouse_device_id";

/** A random id created once per browser, used only so the server can
 * enforce bans by device fingerprint - never used for tracking. */
export function getDeviceId(): string | null {
  try {
    let id = localStorage.getItem(DEVICE_KEY);
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem(DEVICE_KEY, id);
    }
    return id;
  } catch {
    return null;
  }
}
