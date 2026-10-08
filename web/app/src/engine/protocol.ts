// Messages between the page and the engine worker.

export type Stage = "runtime" | "packages" | "engine" | "storage" | "database";
export const STAGES: Stage[] = ["runtime", "packages", "engine", "storage", "database"];

export type ToWorker =
  | { type: "init"; base: string }
  | { type: "call"; id: number; method: string; args?: Record<string, unknown>; files?: File[] };

export type FromWorker =
  | { type: "progress"; stage: Stage; done: number; total: number }
  | { type: "ready"; version: string; persistent: boolean; seconds: number }
  | { type: "fatal"; code: "locked" | "error"; error: string }
  | { type: "result"; id: number; ok: true; result?: unknown; bytes?: Uint8Array }
  | { type: "result"; id: number; ok: false; error: string; trace?: string };
