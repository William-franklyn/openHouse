"use client";

import { useState } from "react";
import { Hash, Plus, ChevronsUpDown, UserPlus, Settings, Music, LogOut, X } from "lucide-react";
import { useRoomStore } from "@/lib/store";
import { Avatar } from "@/components/ui/Avatar";
import { Tooltip } from "@/components/ui/Tooltip";
import { DropdownMenu, DropdownItem, DropdownDivider } from "@/components/ui/DropdownMenu";
import { roleLabel } from "@/lib/roleLabel";
import { MemberRole } from "@/lib/types";

function SidebarContent({
  roomName,
  myName,
  myRole,
  canInvite,
  canManage,
  onCloseMobile,
  onOpenCreateChannel,
  onInvite,
  onSettings,
  onOpenMusicPicker,
  onLogout,
}: {
  roomName: string;
  myName: string;
  myRole: MemberRole | null;
  canInvite: boolean;
  canManage: boolean;
  onCloseMobile: () => void;
  onOpenCreateChannel: () => void;
  onInvite: () => void;
  onSettings: () => void;
  onOpenMusicPicker: () => void;
  onLogout: () => void;
}) {
  const channels = useRoomStore((s) => s.channels);
  const activeChannelId = useRoomStore((s) => s.activeChannelId);
  const canCreateChannel = canManage && channels.length < 11;

  return (
    <div className="flex h-full w-[264px] flex-col bg-sidebar">
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-4">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted">Openhouse</p>
          <h1 className="truncate text-[16px] font-semibold text-foreground">{roomName}</h1>
        </div>
        <button
          type="button"
          onClick={onCloseMobile}
          aria-label="Close menu"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-sm)] text-muted hover:bg-sidebar-hover lg:hidden"
        >
          <X size={18} />
        </button>
      </div>

      <nav aria-label="Channels" className="flex-1 overflow-y-auto px-2.5 py-3">
        <div className="flex items-center justify-between px-2 pb-1.5">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">Channels</span>
          {canCreateChannel && (
            <Tooltip label="New channel">
              <button
                type="button"
                onClick={onOpenCreateChannel}
                aria-label="New channel"
                className="flex h-5 w-5 items-center justify-center rounded text-muted hover:bg-sidebar-hover hover:text-foreground"
              >
                <Plus size={14} />
              </button>
            </Tooltip>
          )}
        </div>
        <ul className="flex flex-col gap-0.5">
          {channels.map((c) => {
            const active = c.id === activeChannelId;
            return (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => {
                    useRoomStore.getState().setActiveChannel(c.id);
                    onCloseMobile();
                  }}
                  aria-current={active ? "page" : undefined}
                  className={`flex w-full items-center gap-2 rounded-[var(--radius-sm)] px-2 py-1.5 text-[14px] transition-colors ${
                    active
                      ? "bg-accent-soft font-medium text-accent"
                      : "text-foreground/80 hover:bg-sidebar-hover"
                  }`}
                >
                  <Hash size={15} className={active ? "text-accent" : "text-muted"} />
                  <span className="truncate">{c.name}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="border-t border-border p-2">
        <DropdownMenu
          align="start"
          placement="up"
          trigger={({ toggle, open }) => (
            <button
              type="button"
              onClick={toggle}
              aria-haspopup="menu"
              aria-expanded={open}
              className="flex w-full items-center gap-2.5 rounded-[var(--radius-md)] px-2 py-2 text-left transition-colors hover:bg-sidebar-hover"
            >
              <Avatar name={myName} size="sm" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] font-medium text-foreground">{myName}</span>
                {myRole && (
                  <span className="flex items-center gap-1">
                    <span className="h-1.5 w-1.5 rounded-full bg-success" />
                    <span className="text-[11px] text-muted">{roleLabel(myRole)}</span>
                  </span>
                )}
              </span>
              <ChevronsUpDown size={14} className="shrink-0 text-muted" />
            </button>
          )}
        >
          {canInvite && (
            <DropdownItem icon={<UserPlus size={15} />} onClick={onInvite}>
              Invite someone
            </DropdownItem>
          )}
          {canManage && (
            <DropdownItem icon={<Music size={15} />} onClick={onOpenMusicPicker}>
              Play music
            </DropdownItem>
          )}
          {canManage && (
            <DropdownItem icon={<Settings size={15} />} onClick={onSettings}>
              Room settings
            </DropdownItem>
          )}
          {(canInvite || canManage) && <DropdownDivider />}
          <DropdownItem icon={<LogOut size={15} />} onClick={onLogout} danger>
            Log out
          </DropdownItem>
        </DropdownMenu>
      </div>
    </div>
  );
}

export function RoomSidebar({
  roomName,
  myName,
  myRole,
  canInvite,
  canManage,
  mobileOpen,
  onCloseMobile,
  onOpenCreateChannel,
  onInvite,
  onSettings,
  onOpenMusicPicker,
  onLogout,
}: {
  roomName: string;
  myName: string;
  myRole: MemberRole | null;
  canInvite: boolean;
  canManage: boolean;
  mobileOpen: boolean;
  onCloseMobile: () => void;
  onOpenCreateChannel: () => void;
  onInvite: () => void;
  onSettings: () => void;
  onOpenMusicPicker: () => void;
  onLogout: () => void;
}) {
  const props = { roomName, myName, myRole, canInvite, canManage, onCloseMobile, onOpenCreateChannel, onInvite, onSettings, onOpenMusicPicker, onLogout };

  return (
    <>
      {/* Desktop: static column. Mobile/tablet: off-canvas drawer. Two
          separate mount points rather than one shared JSX value rendered
          twice in both places - see the equivalent comment in
          OnlineList.tsx for why that duplication is unsafe (it mounts
          two independent instances of anything stateful inside, like a
          <dialog>-backed modal, both reacting to the same prop at once). */}
      <div className="hidden lg:block">
        <SidebarContent {...props} />
      </div>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 animate-fade-in bg-[#191b2a]/45"
            onClick={onCloseMobile}
            aria-hidden
          />
          <div className="absolute inset-y-0 left-0 w-[264px] animate-slide-in-left bg-sidebar shadow-[var(--shadow-lg)]">
            <SidebarContent {...props} />
          </div>
        </div>
      )}
    </>
  );
}
