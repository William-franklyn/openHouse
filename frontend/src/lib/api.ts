import {
  ApiError,
  AdminMetricRow,
  AdminReport,
  CreateRoomResponse,
  DownloadResponse,
  HistoryResponse,
  InviteCreated,
  JoinResponse,
  RecoverResponse,
  ReportResponse,
  RoomDetail,
  RoomPublic,
  UploadResponse,
} from "./types";

// Empty string means "same origin" (relative paths) - correct by default
// when frontend and backend share one domain via Vercel Services routing.
// Local dev sets NEXT_PUBLIC_API_URL explicitly since the two run on
// different ports there.
export function apiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "";
}

export function wsUrl(): string {
  return apiBaseUrl().replace(/^http/, "ws") + "/ws";
}

async function request<T>(
  path: string,
  init: RequestInit & { token?: string } = {}
): Promise<T> {
  const { token, headers, ...rest } = init;
  const resp = await fetch(`${apiBaseUrl()}${path}`, {
    ...rest,
    headers: {
      ...(rest.body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
  });

  const isJson = resp.headers.get("content-type")?.includes("application/json");
  const body = isJson ? await resp.json().catch(() => null) : null;

  if (!resp.ok) {
    const code = body?.code ?? body?.detail ?? "bad_request";
    const message = body?.message ?? resp.statusText;
    throw new ApiError(code, message, resp.status);
  }

  return body as T;
}

export const api = {
  createRoom(input: {
    name: string;
    owner_name?: string | null;
    ends_at?: string | null;
    device_id?: string | null;
  }) {
    return request<CreateRoomResponse>("/api/rooms", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  previewRoom(code: string) {
    return request<RoomPublic>(`/api/rooms/by-code/${encodeURIComponent(code)}`);
  },

  joinRoom(
    code: string,
    input: {
      name?: string | null;
      over_18: boolean;
      invite_code?: string | null;
      device_id?: string | null;
    }
  ) {
    return request<JoinResponse>(`/api/rooms/${encodeURIComponent(code)}/join`, {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  recoverOwner(roomId: string, recoveryCode: string, deviceId?: string | null) {
    return request<RecoverResponse>(`/api/rooms/${roomId}/recover-owner`, {
      method: "POST",
      body: JSON.stringify({ recovery_code: recoveryCode, device_id: deviceId }),
    });
  },

  getRoom(roomId: string, token: string) {
    return request<RoomDetail>(`/api/rooms/${roomId}`, { token });
  },

  patchRoom(
    roomId: string,
    token: string,
    patch: Partial<{
      name: string;
      join_policy: string;
      invite_by: string;
      ends_at: string | null;
    }>
  ) {
    return request<RoomPublic>(`/api/rooms/${roomId}`, {
      method: "PATCH",
      token,
      body: JSON.stringify(patch),
    });
  },

  newCode(roomId: string, token: string) {
    return request<{ code: string }>(`/api/rooms/${roomId}/new-code`, {
      method: "POST",
      token,
    });
  },

  deleteRoom(roomId: string, token: string) {
    return request<{ ok: true }>(`/api/rooms/${roomId}`, { method: "DELETE", token });
  },

  createInvite(roomId: string, token: string) {
    return request<InviteCreated>(`/api/rooms/${roomId}/invites`, {
      method: "POST",
      token,
    });
  },

  history(roomId: string, channelId: string, token: string, beforeSeq?: number) {
    const qs = beforeSeq != null ? `?before_seq=${beforeSeq}` : "";
    return request<HistoryResponse>(
      `/api/rooms/${roomId}/channels/${channelId}/messages${qs}`,
      { token }
    );
  },

  async uploadFile(
    roomId: string,
    token: string,
    file: File,
    channelId: string
  ): Promise<UploadResponse> {
    const form = new FormData();
    form.append("file", file);
    form.append("channel_id", channelId);
    const resp = await fetch(`${apiBaseUrl()}/api/rooms/${roomId}/files`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    });
    const body = await resp.json().catch(() => null);
    if (!resp.ok) {
      throw new ApiError(body?.code ?? "bad_request", body?.message ?? resp.statusText, resp.status);
    }
    return body as UploadResponse;
  },

  downloadFile(fileId: string, token: string) {
    return request<DownloadResponse>(`/api/files/${fileId}`, { token });
  },

  report(
    roomId: string,
    token: string,
    input: { reason: string; target_member_id?: string | null; message_id?: string | null }
  ) {
    return request<ReportResponse>(`/api/rooms/${roomId}/reports`, {
      method: "POST",
      token,
      body: JSON.stringify(input),
    });
  },

  // ---- platform admin ----

  adminReports(adminToken: string) {
    return request<{ reports: AdminReport[] }>("/api/admin/reports", {
      headers: { "X-Admin-Token": adminToken },
    });
  },

  adminResolveReport(reportId: string, adminToken: string) {
    return request<{ ok: true }>(`/api/admin/reports/${reportId}/resolve`, {
      method: "POST",
      headers: { "X-Admin-Token": adminToken },
    });
  },

  adminMetrics(adminToken: string) {
    return request<{ metrics: AdminMetricRow[] }>("/api/admin/metrics", {
      headers: { "X-Admin-Token": adminToken },
    });
  },

  adminDeleteRoom(roomId: string, adminToken: string) {
    return request<{ ok: true }>(`/api/admin/rooms/${roomId}`, {
      method: "DELETE",
      headers: { "X-Admin-Token": adminToken },
    });
  },
};
