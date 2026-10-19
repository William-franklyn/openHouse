"use client";

import { FormEvent, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";

export function CreateChannelModal({
  open,
  onClose,
  onCreate,
}: {
  open: boolean;
  onClose: () => void;
  onCreate: (name: string) => void;
}) {
  const [name, setName] = useState("");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    onCreate(name.trim());
    setName("");
  }

  return (
    <Modal open={open} onClose={onClose} title="New channel">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <Input
          label="Channel name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="find-a-team"
          maxLength={32}
          autoFocus
        />
        <Button type="submit">Create channel</Button>
      </form>
    </Modal>
  );
}
