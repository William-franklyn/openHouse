"use client";

import { ReactNode, useEffect, useRef } from "react";

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
}

/** Built on the native <dialog> element: free focus-trapping, Escape-to-close,
 * and backdrop handling from the browser instead of hand-rolled JS. */
export function Modal({ open, onClose, title, children }: ModalProps) {
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
      className="m-auto w-[min(90vw,420px)] rounded-xl border border-border bg-surface p-5 text-foreground backdrop:bg-black/50"
    >
      <div className="flex items-center justify-between gap-4">
        {title && <h2 className="text-lg font-semibold">{title}</h2>}
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="ml-auto rounded-full p-1 text-muted hover:bg-surface-muted"
        >
          ✕
        </button>
      </div>
      <div className="mt-4">{children}</div>
    </dialog>
  );
}
