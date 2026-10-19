"use client";

import { FormEvent, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { Spinner } from "@/components/ui/Spinner";
import { api } from "@/lib/api";
import { AdminMetricRow, AdminReport, ApiError } from "@/lib/types";

const TOKEN_KEY = "openhouse_admin_token";

export function AdminClient() {
  const [token, setToken] = useState("");
  const [authed, setAuthed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [reports, setReports] = useState<AdminReport[] | null>(null);
  const [metrics, setMetrics] = useState<AdminMetricRow[] | null>(null);
  const [takedownRoomId, setTakedownRoomId] = useState("");

  useEffect(() => {
    try {
      const saved = sessionStorage.getItem(TOKEN_KEY);
      if (saved) {
        setToken(saved);
        setAuthed(true);
      }
    } catch {
      // ignore
    }
  }, []);

  async function refresh(adminToken: string) {
    setError(null);
    try {
      const [reportsRes, metricsRes] = await Promise.all([
        api.adminReports(adminToken),
        api.adminMetrics(adminToken),
      ]);
      setReports(reportsRes.reports);
      setMetrics(metricsRes.metrics);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't load admin data.");
      if (err instanceof ApiError && err.status === 403) {
        setAuthed(false);
        try {
          sessionStorage.removeItem(TOKEN_KEY);
        } catch {
          // ignore
        }
      }
    }
  }

  function handleLogin(e: FormEvent) {
    e.preventDefault();
    try {
      sessionStorage.setItem(TOKEN_KEY, token);
    } catch {
      // ignore
    }
    setAuthed(true);
    refresh(token);
  }

  async function resolveReport(id: string) {
    await api.adminResolveReport(id, token);
    refresh(token);
  }

  async function handleTakedown(e: FormEvent) {
    e.preventDefault();
    if (!takedownRoomId.trim()) return;
    if (!confirm(`Delete room ${takedownRoomId}? This erases its messages and files.`)) return;
    try {
      await api.adminDeleteRoom(takedownRoomId.trim(), token);
      setTakedownRoomId("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't delete that room.");
    }
  }

  if (!authed) {
    return (
      <div className="mx-auto max-w-sm px-4 py-16">
        <h1 className="text-xl font-semibold">Platform admin</h1>
        <form onSubmit={handleLogin} className="mt-6 flex flex-col gap-4">
          <Input
            label="Admin token"
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            autoFocus
          />
          <Button type="submit" disabled={!token}>
            Sign in
          </Button>
        </form>
      </div>
    );
  }

  const metricsByDay = (metrics ?? []).reduce<Record<string, Record<string, number>>>((acc, row) => {
    acc[row.day] = acc[row.day] ?? {};
    acc[row.day][row.name] = row.value;
    return acc;
  }, {});
  const metricNames = Array.from(new Set((metrics ?? []).map((m) => m.name))).sort();
  const days = Object.keys(metricsByDay).sort().reverse();

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Platform admin</h1>
        <Button variant="ghost" size="sm" onClick={() => refresh(token)}>
          Refresh
        </Button>
      </div>
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}

      <section className="mt-8">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Reports</h2>
        {!reports ? (
          <Spinner className="mt-4 h-5 w-5 text-accent" />
        ) : reports.length === 0 ? (
          <p className="mt-2 text-sm text-muted">No reports.</p>
        ) : (
          <div className="mt-3 flex flex-col gap-2">
            {reports.map((r) => (
              <div key={r.id} className="rounded-lg border border-border bg-surface p-3 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <Badge tone={r.status === "open" ? "danger" : "default"}>{r.status}</Badge>
                  <span className="text-xs text-muted">{new Date(r.created_at).toLocaleString()}</span>
                </div>
                <p className="mt-2">{r.reason}</p>
                <p className="mt-1 text-xs text-muted">
                  Room {r.room_id} · reported by {r.reporter_member_id}
                  {r.target_member_id && ` · member ${r.target_member_id}`}
                  {r.message_id && ` · message ${r.message_id}`}
                </p>
                {r.status === "open" && (
                  <Button size="sm" variant="secondary" className="mt-2" onClick={() => resolveReport(r.id)}>
                    Mark resolved
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="mt-8">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Daily metrics</h2>
        {!metrics ? (
          <Spinner className="mt-4 h-5 w-5 text-accent" />
        ) : days.length === 0 ? (
          <p className="mt-2 text-sm text-muted">No metrics yet.</p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border text-xs uppercase text-muted">
                  <th className="py-2 pr-4">Day</th>
                  {metricNames.map((name) => (
                    <th key={name} className="py-2 pr-4">
                      {name.replace(/_/g, " ")}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {days.map((day) => (
                  <tr key={day} className="border-b border-border/50">
                    <td className="py-2 pr-4 font-mono text-xs">{day}</td>
                    {metricNames.map((name) => (
                      <td key={name} className="py-2 pr-4">
                        {metricsByDay[day][name] ?? 0}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="mt-8">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Takedown</h2>
        <form onSubmit={handleTakedown} className="mt-3 flex items-end gap-2">
          <Input
            value={takedownRoomId}
            onChange={(e) => setTakedownRoomId(e.target.value)}
            placeholder="Room ID"
            className="flex-1"
          />
          <Button type="submit" variant="danger">
            Delete room
          </Button>
        </form>
      </section>
    </div>
  );
}
