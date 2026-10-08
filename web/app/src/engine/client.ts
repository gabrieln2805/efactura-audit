// The page's side of the engine: starts the worker on first use (or start()) and turns calls into promises.
import type { FromWorker, Stage } from "./protocol";

export type EngineState =
  | { phase: "loading"; stage: Stage; done: number; total: number }
  | { phase: "ready"; version: string; persistent: boolean; seconds: number; stages: Record<string, number> }
  | { phase: "locked" }
  | { phase: "error"; error: string };

export class EngineError extends Error {
  constructor(message: string, readonly trace?: string) {
    super(message);
  }
}

type Pending = { resolve: (v: any) => void; reject: (e: unknown) => void; onLog?: (text: string) => void };

export class Engine {
  state: EngineState = { phase: "loading", stage: "runtime", done: 0, total: 0 };
  private worker: Worker | null = null;
  private nextId = 1;
  private pending = new Map<number, Pending>();
  private listeners = new Set<(s: EngineState) => void>();

  /** Start loading Pyodide and the engine (about 50 MB on a first visit). Safe to call repeatedly. */
  start(): Worker {
    if (this.worker) return this.worker;
    const w = new Worker(new URL("./worker.ts", import.meta.url), { type: "module" });
    w.onmessage = (ev: MessageEvent<FromWorker>) => this.receive(ev.data);
    w.onerror = (ev) => this.setState({ phase: "error", error: ev.message || "worker failed" });
    w.postMessage({ type: "init", base: document.baseURI,
                    storage: new URLSearchParams(location.search).get("storage") ?? undefined });
    this.worker = w;
    return w;
  }

  get started(): boolean {
    return this.worker !== null;
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
        this.setState({ phase: "ready", version: m.version, persistent: m.persistent, seconds: m.seconds, stages: m.stages });
        break;
      case "log":
        this.pending.get(m.id)?.onLog?.(m.text);
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
  call<T = unknown>(method: string, args: Record<string, unknown> = {}, files?: File[],
                    onLog?: (text: string) => void): Promise<T> {
    const id = this.nextId++;
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve, reject, onLog });
      this.start().postMessage({ type: "call", id, method, args, files });
    });
  }
}
