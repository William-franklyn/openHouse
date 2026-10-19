"use client";

import { useEffect } from "react";
import { useRoomStore } from "@/lib/store";

export function ErrorToast() {
  const error = useRoomStore((s) => s.lastError);
  const clearError = useRoomStore((s) => s.clearError);

  useEffect(() => {
    if (!error) return;
    const timer = setTimeout(clearError, 4000);
    return () => clearTimeout(timer);
  }, [error, clearError]);

  if (!error) return null;

  return (
    <div className="fixed inset-x-0 bottom-4 z-50 flex justify-center px-4">
      <div className="rounded-lg bg-danger px-4 py-2.5 text-sm text-white shadow-lg">
        {error.message}
      </div>
    </div>
  );
}
