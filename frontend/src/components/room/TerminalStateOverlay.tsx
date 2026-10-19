"use client";

import { useRouter } from "next/navigation";
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
      <div className="max-w-sm text-center">
        <p className="text-lg font-semibold">{message}</p>
        <Button className="mt-6" onClick={handleHome}>
          Back home
        </Button>
      </div>
    </div>
  );
}
