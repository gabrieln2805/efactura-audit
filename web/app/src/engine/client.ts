// The page's side of the engine: starts the worker at once and turns calls into promises.
import type { FromWorker, Stage } from "./protocol";

export type EngineState =
  | { phase: "loading"; stage: Stage; done: number; total: number }
  | { phase: "ready"; version: string; persistent: boolean; seconds: number }
  | { phase: "locked" }
  | { phase: "error"; error: string };

export class EngineError extends Error {
  constructor(message: string, readonly trace?: string) {
    super(message);
  }
}

type Pending = { resolve: (v: any) => void; reject: (e: unknown) => void };

export class Engine {
  state: EngineState = { phase: "loading", stage: "runtime", done: 0, total: 0 };
  private worker: Worker;
  private nextId = 1;
  private pending = new Map<number, Pending>();
  private listeners = new Set<(s: EngineState) => void>();

  constructor() {
    this.worker = new Worker(new URL("./worker.ts", import.meta.url), { type: "module" });
    this.worker.onmessage = (ev: MessageEvent<FromWorker>) => this.receive(ev.data);
    this.worker.onerror = (ev) => this.setState({ phase: "error", error: ev.message || "worker failed" });
    this.worker.postMessage({ type: "init", base: document.baseURI });
  }

  subscribe(fn: (s: EngineState) => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private setState(s: EngineState) {
    this.state = s;
    this.listeners.forEach((fn) => fn(s));
  }

  private receive(m: FromWorker) {
    switch (m.type) {
      case "progress":
        this.setState({ phase: "loading", stage: m.stage, done: m.done, total: m.total });
        break;
      case "ready":
        this.setState({ phase: "ready", version: m.version, persistent: m.persistent, seconds: m.seconds });
        break;
      case "fatal":
        this.setState(m.code === "locked" ? { phase: "locked" } : { phase: "error", error: m.error });
        for (const p of this.pending.values()) p.reject(new EngineError(m.error));
        this.pending.clear();
        break;
      case "result": {
        const p = this.pending.get(m.id);
        if (!p) return;
        this.pending.delete(m.id);
        if (m.ok) p.resolve(m.bytes ?? m.result);
        else p.reject(new EngineError(m.error, m.trace));
      }
    }
  }

  /** Call one method of efactura_audit.web.Api. Waits for the engine to be ready. */
  call<T = unknown>(method: string, args: Record<string, unknown> = {}, files?: File[]): Promise<T> {
    const id = this.nextId++;
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.worker.postMessage({ type: "call", id, method, args, files });
    });
  }
}
