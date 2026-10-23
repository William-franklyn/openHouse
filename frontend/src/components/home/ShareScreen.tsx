"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { Button } from "@/components/ui/Button";

export function ShareScreen({
  roomId,
  roomName,
  code,
  recoveryCode,
}: {
  roomId: string;
  roomName: string;
  code: string;
  recoveryCode: string;
}) {
  const router = useRouter();
  const [savedRecovery, setSavedRecovery] = useState(false);
  const [copied, setCopied] = useState<"code" | "link" | "recovery" | null>(null);

  const joinLink = typeof window !== "undefined" ? `${window.location.origin}/r/${code}` : "";
  const hotspotName = `Openhouse ${code}`;

  function copy(value: string, which: typeof copied) {
    navigator.clipboard?.writeText(value).then(() => {
      setCopied(which);
      setTimeout(() => setCopied(null), 1500);
    });
  }

  return (
    <div className="mx-auto flex max-w-md flex-col gap-6 px-4 py-8 print:max-w-full">
      <div className="text-center">
        <h1 className="text-xl font-semibold">{roomName} is ready</h1>
        <p className="text-sm text-muted">Share this with the people you want in the room.</p>
      </div>

      <div className="flex flex-col items-center gap-3 rounded-xl border border-border bg-surface p-6">
        <div className="font-mono text-5xl font-bold tracking-widest">{code}</div>
        <button
          type="button"
          onClick={() => copy(code, "code")}
          className="text-sm text-accent underline"
        >
          {copied === "code" ? "Copied!" : "Copy code"}
        </button>

        <div className="mt-2 rounded-lg bg-white p-3 print:shadow-none">
          <QRCodeSVG value={joinLink} size={180} />
        </div>

        <div className="flex items-center gap-2 text-sm text-muted">
          <span className="truncate">{joinLink}</span>
          <button type="button" onClick={() => copy(joinLink, "link")} className="shrink-0 text-accent underline">
            {copied === "link" ? "Copied!" : "Copy link"}
          </button>
        </div>
      </div>

      <Button variant="secondary" onClick={() => window.print()} className="print:hidden">
        Print poster
      </Button>

      <details className="rounded-xl border border-border bg-surface p-4 text-sm print:hidden">
        <summary className="cursor-pointer font-medium">Advertise with your hotspot</summary>
        <div className="mt-3 flex flex-col gap-3 text-muted">
          <p>
            Rename your phone&apos;s hotspot to{" "}
            <span className="font-mono font-semibold text-foreground">{hotspotName}</span>. People
            nearby will see it in their Wi-Fi list, but nobody needs to connect to it - they just
            read the code and type it in here.
          </p>
          <p>
            <strong className="text-foreground">iPhone:</strong> Settings → General → About → Name
            (this is also your hotspot name)
          </p>
          <p>
            <strong className="text-foreground">Android:</strong> Settings → Hotspot → Hotspot name
          </p>
          <p className="text-xs">Your hotspot uses battery - turn it off when you&apos;re done.</p>
        </div>
      </details>

      <div className="rounded-xl border border-danger/40 bg-surface p-4 print:hidden">
        <h2 className="font-semibold">House owner recovery code</h2>
        <p className="mt-1 text-sm text-muted">
          Save this somewhere safe. If you lose this device, entering this code gets you house
          owner access back.
        </p>
        <div className="mt-3 flex items-center justify-between gap-2 rounded-lg bg-surface-muted px-3 py-2">
          <span className="font-mono text-lg tracking-wide">{recoveryCode}</span>
          <button type="button" onClick={() => copy(recoveryCode, "recovery")} className="text-sm text-accent underline">
            {copied === "recovery" ? "Copied!" : "Copy"}
          </button>
        </div>
        {!savedRecovery && (
          <Button className="mt-3 w-full" onClick={() => setSavedRecovery(true)}>
            I saved it
          </Button>
        )}
      </div>

      <Button
        size="md"
        disabled={!savedRecovery}
        onClick={() => router.push(`/room/${roomId}`)}
        className="print:hidden"
      >
        Enter the room
      </Button>
    </div>
  );
}
