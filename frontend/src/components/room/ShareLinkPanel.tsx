"use client";

import { useState } from "react";
import { Check, Copy, Mail, MessageCircle, Share2 } from "lucide-react";

/** A link display + copy button + WhatsApp/email/LinkedIn share-intent
 * buttons - all client-side share URLs, no API calls or auth needed. */
export function ShareLinkPanel({
  link,
  shareText,
  dark,
}: {
  link: string;
  shareText: string;
  dark?: boolean;
}) {
  const [copied, setCopied] = useState(false);

  function copy() {
    navigator.clipboard?.writeText(link).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  const waUrl = `https://wa.me/?text=${encodeURIComponent(`${shareText} ${link}`)}`;
  const mailUrl = `mailto:?subject=${encodeURIComponent("Play chess with me on Openhouse")}&body=${encodeURIComponent(`${shareText}\n\n${link}`)}`;
  const linkedinUrl = `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(link)}`;

  const boxClass = dark
    ? "border-white/15 bg-white/5 text-white"
    : "border-border bg-surface-muted text-foreground";
  const mutedClass = dark ? "text-white/50" : "text-muted";
  const circleClass = dark
    ? "border-white/15 bg-white/5 text-white/80 hover:bg-white/10"
    : "border-border bg-surface text-foreground hover:bg-surface-muted";

  return (
    <div className="flex w-full flex-col gap-4">
      {/* Full link, wrapped rather than truncated - nothing hidden. */}
      <div className={`rounded-[var(--radius-md)] border px-3.5 py-3 ${boxClass}`}>
        <p className={`mb-1 text-[10px] font-semibold uppercase tracking-wide ${mutedClass}`}>Invite link</p>
        <p className="break-all text-[12.5px] leading-snug">{link}</p>
      </div>

      <button
        type="button"
        onClick={copy}
        className={`flex items-center justify-center gap-1.5 rounded-[var(--radius-md)] border px-3 py-2.5 text-[13px] font-semibold transition-colors ${
          dark
            ? "border-violet-400/40 bg-violet-500/15 text-violet-200 hover:bg-violet-500/25"
            : "border-accent/30 bg-accent-soft text-accent hover:border-accent"
        }`}
      >
        {copied ? <Check size={14} /> : <Copy size={14} />}
        {copied ? "Copied!" : "Copy link"}
      </button>

      <div className="flex items-start justify-center gap-5">
        <a
          href={waUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="flex flex-col items-center gap-1.5"
        >
          <span className={`flex h-11 w-11 items-center justify-center rounded-full border transition-colors ${circleClass}`}>
            <MessageCircle size={17} />
          </span>
          <span className={`text-[11px] font-medium ${mutedClass}`}>WhatsApp</span>
        </a>
        <a href={mailUrl} className="flex flex-col items-center gap-1.5">
          <span className={`flex h-11 w-11 items-center justify-center rounded-full border transition-colors ${circleClass}`}>
            <Mail size={17} />
          </span>
          <span className={`text-[11px] font-medium ${mutedClass}`}>Email</span>
        </a>
        <a
          href={linkedinUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="flex flex-col items-center gap-1.5"
        >
          <span className={`flex h-11 w-11 items-center justify-center rounded-full border transition-colors ${circleClass}`}>
            <Share2 size={17} />
          </span>
          <span className={`text-[11px] font-medium ${mutedClass}`}>LinkedIn</span>
        </a>
      </div>
    </div>
  );
}
