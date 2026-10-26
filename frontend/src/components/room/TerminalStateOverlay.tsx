"use client";

import { useRouter } from "next/navigation";
import { DoorClosed } from "lucide-react";
import { clearSession } from "@/lib/session";
import { Button } from "@/components/ui/Button";

export function TerminalStateOverlay({
  roomId,
  message,
}: {
  roomId: string;
  message: string;
}) {
  const router = useRouter();

  function handleHome() {
    clearSession(roomId);
    router.push("/");
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background p-6">
      <div className="flex max-w-sm flex-col items-center gap-3 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-surface-muted">
          <DoorClosed size={22} className="text-muted" />
        </div>
        <p className="text-[16px] font-semibold text-foreground">{message}</p>
        <Button className="mt-2" onClick={handleHome}>
          Back home
        </Button>
      </div>
    </div>
  );
}
