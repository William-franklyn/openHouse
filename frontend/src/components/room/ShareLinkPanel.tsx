"use client";

import { useState } from "react";
import { Check, Copy, Link2, Mail, MessageCircle, Share2 } from "lucide-react";

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

  return (
    <div className="flex flex-col gap-3">
      <div className={`flex items-center gap-2 rounded-[var(--radius-md)] border px-3 py-2.5 ${boxClass}`}>
        <Link2 size={14} className={`shrink-0 ${mutedClass}`} />
        <span className="min-w-0 flex-1 truncate text-[13px]">{link}</span>
      </div>

      <button
        type="button"
        onClick={copy}
        className={`flex items-center justify-center gap-1.5 rounded-[var(--radius-md)] border px-3 py-2 text-[13px] font-semibold transition-colors ${
          dark
            ? "border-violet-400/40 bg-violet-500/15 text-violet-200 hover:bg-violet-500/25"
            : "border-accent/30 bg-accent-soft text-accent hover:border-accent"
        }`}
      >
        {copied ? <Check size={14} /> : <Copy size={14} />}
        {copied ? "Copied!" : "Copy link"}
      </button>

      <div className="flex items-center gap-2">
        <a
          href={waUrl}
          target="_blank"
          rel="noopener noreferrer"
          className={`flex flex-1 items-center justify-center gap-1.5 rounded-[var(--radius-md)] border px-2 py-2 text-[12px] font-medium transition-colors ${
            dark ? "border-white/15 text-white/70 hover:bg-white/10" : "border-border text-muted hover:bg-surface-muted"
          }`}
        >
          <MessageCircle size={13} /> WhatsApp
        </a>
        <a
          href={mailUrl}
          className={`flex flex-1 items-center justify-center gap-1.5 rounded-[var(--radius-md)] border px-2 py-2 text-[12px] font-medium transition-colors ${
            dark ? "border-white/15 text-white/70 hover:bg-white/10" : "border-border text-muted hover:bg-surface-muted"
          }`}
        >
          <Mail size={13} /> Email
        </a>
        <a
          href={linkedinUrl}
          target="_blank"
          rel="noopener noreferrer"
          className={`flex flex-1 items-center justify-center gap-1.5 rounded-[var(--radius-md)] border px-2 py-2 text-[12px] font-medium transition-colors ${
            dark ? "border-white/15 text-white/70 hover:bg-white/10" : "border-border text-muted hover:bg-surface-muted"
          }`}
        >
          <Share2 size={13} /> LinkedIn
        </a>
      </div>
    </div>
  );
}
