"use client";

// Synthesized via the Web Audio API, not audio files - no assets to host
// or license, and the file-upload-derived music pipeline (Room DJ) would
// be overkill for a handful of short UI blips.

let ctx: AudioContext | null = null;

function getContext(): AudioContext | null {
  if (typeof window === "undefined") return null;
  const AudioContextClass = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioContextClass) return null;
  if (!ctx) ctx = new AudioContextClass();
  // Browsers suspend a freshly-created context until a user gesture -
  // every call site here only ever fires from a click or a server event
  // that followed one, so resuming is always safe to attempt.
  if (ctx.state === "suspended") ctx.resume().catch(() => {});
  return ctx;
}

function tone(freq: number, startOffset: number, duration: number, type: OscillatorType, gainPeak: number) {
  const audioCtx = getContext();
  if (!audioCtx) return;
  const osc = audioCtx.createOscillator();
  const gain = audioCtx.createGain();
  osc.type = type;
  osc.frequency.value = freq;
  const start = audioCtx.currentTime + startOffset;
  gain.gain.setValueAtTime(0, start);
  gain.gain.linearRampToValueAtTime(gainPeak, start + 0.012);
  gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);
  osc.connect(gain);
  gain.connect(audioCtx.destination);
  osc.start(start);
  osc.stop(start + duration + 0.02);
}

let enabled = true;

export function setChessSoundEnabled(value: boolean) {
  enabled = value;
}

export function isChessSoundEnabled() {
  return enabled;
}

export function playMoveSound() {
  if (!enabled) return;
  tone(520, 0, 0.09, "sine", 0.18);
}

export function playCaptureSound() {
  if (!enabled) return;
  tone(300, 0, 0.1, "square", 0.14);
  tone(180, 0.03, 0.12, "square", 0.12);
}

export function playCheckSound() {
  if (!enabled) return;
  tone(880, 0, 0.1, "triangle", 0.16);
  tone(660, 0.08, 0.12, "triangle", 0.14);
}

export function playGameStartSound() {
  if (!enabled) return;
  tone(440, 0, 0.1, "sine", 0.15);
  tone(660, 0.08, 0.12, "sine", 0.15);
  tone(880, 0.16, 0.16, "sine", 0.15);
}

export function playWinSound() {
  if (!enabled) return;
  [523, 659, 784, 1047].forEach((freq, i) => tone(freq, i * 0.09, 0.22, "triangle", 0.2));
}

export function playLoseSound() {
  if (!enabled) return;
  [392, 330, 262].forEach((freq, i) => tone(freq, i * 0.11, 0.3, "sine", 0.16));
}

export function playDrawSound() {
  if (!enabled) return;
  tone(440, 0, 0.18, "sine", 0.15);
  tone(440, 0.2, 0.22, "sine", 0.13);
}
