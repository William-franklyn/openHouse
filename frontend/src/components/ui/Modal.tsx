"use client";

import { ReactNode, useEffect, useRef } from "react";
import { X } from "lucide-react";

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  // Every other modal is a short form/confirmation, where the default
  // 420px reads fine - GamesModal is the one exception needing room for
  // a real grid of cards, so this stays optional rather than making
  // every call site think about sizing.
  maxWidthClassName?: string;
}

/** Built on the native <dialog> element: free focus-trapping, Escape-to-close,
 * and backdrop handling from the browser instead of hand-rolled JS. */
export function Modal({ open, onClose, title, children, maxWidthClassName }: ModalProps) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onCancel={onClose}
      className={`m-auto ${maxWidthClassName ?? "w-[min(92vw,420px)]"} rounded-[var(--radius-lg)] border border-border bg-surface p-5 text-foreground shadow-[var(--shadow-lg)] backdrop:bg-[#191b2a]/45 open:animate-slide-up`}
    >
      <div className="flex items-center justify-between gap-4">
        {title && <h2 className="text-[17px] font-semibold">{title}</h2>}
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="ml-auto flex h-7 w-7 items-center justify-center rounded-full text-muted transition-colors hover:bg-surface-muted hover:text-foreground"
        >
          <X size={16} strokeWidth={2} />
        </button>
      </div>
      <div className="mt-4">{children}</div>
    </dialog>
  );
}
