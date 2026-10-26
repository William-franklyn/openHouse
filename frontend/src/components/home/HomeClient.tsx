"use client";

import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { QrCode, DoorOpen } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { CreateRoomModal } from "./CreateRoomModal";
import { QrScanner } from "./QrScanner";
import { ShareScreen } from "./ShareScreen";
import { CreateRoomResponse } from "@/lib/types";

function extractCode(raw: string): string {
  const trimmed = raw.trim();
  try {
    const url = new URL(trimmed);
    const match = url.pathname.match(/\/r\/([A-Za-z0-9]+)/);
    if (match) return match[1].toUpperCase();
  } catch {
    // not a URL, fall through to treating it as a bare code
  }
  return trimmed.toUpperCase();
}

export function HomeClient() {
  const router = useRouter();
  const [code, setCode] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [showScan, setShowScan] = useState(false);
  const [created, setCreated] = useState<CreateRoomResponse | null>(null);

  const handleScanned = useCallback(
    (value: string) => {
      setShowScan(false);
      router.push(`/r/${extractCode(value)}`);
    },
    [router]
  );

  function goToCode() {
    const value = extractCode(code);
    if (value) router.push(`/r/${value}`);
  }

  if (created) {
    return (
      <ShareScreen
        roomId={created.room.id}
        roomName={created.room.name}
        code={created.room.code}
        recoveryCode={created.recovery_code}
      />
    );
  }

  return (
    <div className="mx-auto flex max-w-sm flex-col gap-6 px-4 py-12">
      <div className="text-center">
        <h1 className="text-2xl font-bold">Openhouse</h1>
        <p className="mt-1 text-sm text-muted">
          Chat with the people around you. No phone number, no account, just a code.
        </p>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          goToCode();
        }}
        className="flex flex-col gap-3"
      >
        <Input
          label="Enter Room code"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="4F7K2"
          maxLength={6}
          className="text-center font-mono text-lg tracking-widest uppercase"
          autoCapitalize="characters"
        />
        <Button type="submit" disabled={!code.trim()}>
          Join
        </Button>
      </form>

      <Button variant="secondary" onClick={() => setShowScan(true)}>
        <QrCode size={16} />
        Scan QR code
      </Button>

      <div className="flex items-center gap-3 text-xs text-muted">
        <div className="h-px flex-1 bg-border" />
        or
        <div className="h-px flex-1 bg-border" />
      </div>

      <Button variant="ghost" onClick={() => setShowCreate(true)}>
        <DoorOpen size={16} />
        Create a Room
      </Button>

      <CreateRoomModal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={(result) => {
          setShowCreate(false);
          setCreated(result);
        }}
      />
      <QrScanner open={showScan} onClose={() => setShowScan(false)} onDetected={handleScanned} />
    </div>
  );
}
