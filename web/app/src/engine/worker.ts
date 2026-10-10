/// <reference lib="webworker" />
// The audit engine in a Web Worker: Pyodide + the efactura_audit wheel, with the database kept in the
// browser's private file storage (OPFS). The page starts this worker as soon as it opens; calls wait
// until the engine is ready. Protocol: see ./protocol.ts.
import type { FromWorker, ToWorker, Stage } from "./protocol";

declare const self: DedicatedWorkerGlobalScope;

const PYODIDE_URL: string = import.meta.env.VITE_PYODIDE_URL ?? "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";
const DATA_DIR = "/data";
const LOCK = "efactura-audit-db";
// methods that write to the database: the file is flushed to OPFS after each
// methods that run the audit need scikit-learn, which loads in the background after start-up
const NEEDS_AUDIT = new Set(["load_demo", "import_files", "run_audit", "model_test", "delete_import", "keep_buyer"]);
const WRITES = new Set(["load_demo", "import_files", "run_audit", "set_feedback", "reset", "rerun_tests", "model_test",
                        "delete_import", "keep_buyer"]);

type Manifest = { wheel: string; version: string; hash: string; packages: string[]; audit_packages: string[];
                  report_packages: { pyodide: string[]; pypi: string[] } };
// minimal view of the Pyodide API used here
type PyProxy = { toJs(): unknown; destroy(): void; type: string };
type Pyodide = {
  loadPackage(names: string[], opts?: { messageCallback?: (m: string) => void; errorCallback?: (m: string) => void }): Promise<unknown>;
  unpackArchive(buffer: ArrayBuffer, format: string): void;
  runPythonAsync(code: string): Promise<unknown>;
  pyimport(name: string): any;
  mountNativeFS(path: string, handle: FileSystemDirectoryHandle): Promise<{ syncfs(): Promise<void> }>;
  FS: { mkdirTree(p: string): void; writeFile(p: string, data: Uint8Array): void; unlink(p: string): void;
        rmdir(p: string): void; readdir(p: string): string[]; readFile(p: string): Uint8Array;
        stat(p: string): { mode: number; mtime: Date }; isFile(mode: number): boolean };
  globals: { get(name: string): any };
};

const post = (m: FromWorker, transfer: Transferable[] = []) => self.postMessage(m, transfer);
const stageTimes: Record<string, number> = {};
let stageStart = performance.now();
let lastStage = "";
const progress = (stage: Stage, done = 0, total = 0) => {
  if (stage !== lastStage) {
    const now = performance.now();
    if (lastStage) stageTimes[lastStage] = +((now - stageStart) / 1000).toFixed(2);
    stageStart = now;
    lastStage = stage;
  }
  post({ type: "progress", stage, done, total });
};

let py: Pyodide;
let api: any;
let flush: () => Promise<void> = async () => {};
let persistent = false;
let manifest: Manifest;
let reportsReady: Promise<void> | null = null;
let auditReady: Promise<unknown> | null = null;
let queue: Promise<unknown> = Promise.resolve();   // one engine call at a time
let currentId = 0;   // the call that progress lines belong to

async function acquireLock(): Promise<boolean> {
  // a second tab would open its own copy of the database and the two would overwrite each other
  if (!navigator.locks) return true;
  return new Promise((resolve) => {
    navigator.locks.request(LOCK, { ifAvailable: true }, (lock) => {
      resolve(lock !== null);
      return lock ? new Promise(() => {}) : undefined;   // hold it for the worker's lifetime
    });
  });
}

/** Keep DATA_DIR in OPFS. Pyodide's native mount needs createWritable; browsers without it (older Safari) get
 *  a copy of each changed file written through a synchronous access handle after every write call. */
async function persist(dir: FileSystemDirectoryHandle, mode: "auto" | "snapshot"): Promise<void> {
  if (mode === "auto" && "createWritable" in FileSystemFileHandle.prototype) {
    const fs = await py.mountNativeFS(DATA_DIR, dir);
    flush = () => fs.syncfs();
    return;
  }
  type SyncHandle = { getSize(): number; read(b: Uint8Array, o: { at: number }): number; write(b: Uint8Array, o: { at: number }): number;
                      truncate(n: number): void; flush(): void; close(): void };
  const open = async (name: string) =>
    (await (await dir.getFileHandle(name, { create: true })) as any).createSyncAccessHandle() as Promise<SyncHandle>;
  const saved = new Map<string, number>();   // file -> mtime last written to OPFS
  for await (const [name, handle] of (dir as any).entries() as AsyncIterable<[string, FileSystemHandle]>) {
    if (handle.kind !== "file") continue;
    const h = await open(name);
    const buf = new Uint8Array(h.getSize());
    h.read(buf, { at: 0 });
    h.close();
    py.FS.writeFile(`${DATA_DIR}/${name}`, buf);
    saved.set(name, py.FS.stat(`${DATA_DIR}/${name}`).mtime.getTime());
  }
  flush = async () => {
    const present = new Set<string>();
    for (const name of py.FS.readdir(DATA_DIR)) {
      const path = `${DATA_DIR}/${name}`;
      const st = py.FS.stat(path);
      if (!py.FS.isFile(st.mode)) continue;
      present.add(name);
      if (saved.get(name) === st.mtime.getTime()) continue;
      const data = py.FS.readFile(path);
      const h = await open(name);
      h.truncate(0);
      h.write(data, { at: 0 });
      h.flush();
      h.close();
      saved.set(name, st.mtime.getTime());
    }
    for (const name of [...saved.keys()].filter((n) => !present.has(n))) {   // e.g. a DuckDB WAL file, now merged
      await dir.removeEntry(name).catch(() => {});
      saved.delete(name);
    }
  };
}

async function boot(base: string, storage: "auto" | "snapshot"): Promise<void> {
  const t0 = performance.now();
  progress("runtime");
  const { loadPyodide } = await import(/* @vite-ignore */ `${PYODIDE_URL}pyodide.mjs`);
  py = await loadPyodide({ indexURL: PYODIDE_URL });

  manifest = await (await fetch(new URL("py/manifest.json", base), { cache: "no-cache" })).json();
  let total = manifest.packages.length;
  let done = 0;
  progress("packages", 0, total);
  await py.loadPackage(manifest.packages, {
    messageCallback: (m: string) => {
      const loading = /^Loading (.+)$/.exec(m);
      if (loading) total = loading[1].split(", ").length;
      if (m.startsWith("Loaded ")) done = total;
      else if (/^Loaded|^Fetched|^Downloaded/.test(m)) done += 1;
      progress("packages", Math.min(done, total), total);
    },
    errorCallback: () => {},
  });

  progress("engine");
  const wheel = await fetch(new URL(`py/${manifest.wheel}?v=${manifest.hash}`, base));
  if (!wheel.ok) throw new Error(`engine wheel: HTTP ${wheel.status}`);
  py.unpackArchive(await wheel.arrayBuffer(), "wheel");

  progress("storage");
  if (!(await acquireLock())) {
    post({ type: "fatal", code: "locked", error: "open in another tab" });
    return;
  }
  py.FS.mkdirTree(DATA_DIR);
  try {
    const root = await navigator.storage.getDirectory();
    const dir = await root.getDirectoryHandle("efactura-audit", { create: true });
    await persist(dir, storage);
    persistent = true;
  } catch (e) {
    // no OPFS (old browser, some private windows): the engine still works, data lasts for this visit
    console.warn("OPFS unavailable, data will not be kept", e);
  }

  progress("database");
  (py.globals as any).set("_emit", (text: string) => post({ type: "log", id: currentId, text: String(text) }));
  api = await py.runPythonAsync(`
from efactura_audit.web import Api
api = Api("${DATA_DIR}")
api._progress = _emit
api.hosted_url = "${new URL("api/assistant", base).href}"
api
`);
  await flush();   // a first visit creates the database; a new version may have rebuilt the models
  progress("database");
  stageTimes.database = +((performance.now() - stageStart) / 1000).toFixed(2);
  post({ type: "ready", version: manifest.version, persistent, stages: stageTimes,
         seconds: (performance.now() - t0) / 1000 });
  ensureAuditPackages();   // in the background: the first screens only read
}

function ensureAuditPackages(): Promise<unknown> {
  return (auditReady ??= py.loadPackage(manifest.audit_packages));
}

async function ensureReportPackages(): Promise<void> {
  reportsReady ??= (async () => {
    await py.loadPackage(["micropip", ...manifest.report_packages.pyodide]);
    await py.pyimport("micropip").install(manifest.report_packages.pypi);
  })();
  return reportsReady;
}

async function writeUploads(files: File[]): Promise<string[]> {
  const dir = `/tmp/uploads-${Date.now()}`;
  py.FS.mkdirTree(dir);
  const paths: string[] = [];
  for (const [i, f] of files.entries()) {
    const path = `${dir}/${i}-${f.name.replace(/[\\/]/g, "_")}`;
    py.FS.writeFile(path, new Uint8Array(await f.arrayBuffer()));
    paths.push(path);
  }
  return paths;
}

function removeUploads(paths: string[]): void {
  for (const p of paths) py.FS.unlink(p);
  if (paths.length) py.FS.rmdir(paths[0].slice(0, paths[0].lastIndexOf("/")));
}

async function handle(msg: Extract<ToWorker, { type: "call" }>): Promise<void> {
  const args = { ...(msg.args ?? {}) };
  let uploads: string[] = [];
  try {
    if (msg.files?.length) {
      uploads = await writeUploads(msg.files);
      args.paths = uploads;
    }
    if (NEEDS_AUDIT.has(msg.method)) await ensureAuditPackages();
    if (msg.method === "report") await ensureReportPackages();
    currentId = msg.id;
    const out = api.call(msg.method, JSON.stringify(args));
    if (WRITES.has(msg.method)) await flush();
    if (typeof out === "string") {
      const parsed = JSON.parse(out);
      post(parsed.ok ? { type: "result", id: msg.id, ok: true, result: parsed.result }
                     : { type: "result", id: msg.id, ok: false, error: parsed.error, trace: parsed.trace });
    } else {
      const proxy = out as PyProxy;
      const bytes = proxy.toJs() as Uint8Array;
      proxy.destroy();
      post({ type: "result", id: msg.id, ok: true, bytes }, [bytes.buffer as ArrayBuffer]);
    }
  } catch (e) {
    post({ type: "result", id: msg.id, ok: false, error: String(e).slice(-2000) });
  } finally {
    if (uploads.length) removeUploads(uploads);
  }
}

let booted: Promise<void> = new Promise(() => {});

self.onmessage = (ev: MessageEvent<ToWorker>) => {
  const msg = ev.data;
  if (msg.type === "init") {
    // the page sends its own URL first: the wheel and manifest are served next to it
    booted = boot(msg.base, msg.storage === "snapshot" ? "snapshot" : "auto").catch((e) => {
      post({ type: "fatal", code: "error", error: String(e).slice(-2000) });
      throw e;
    });
    return;
  }
  queue = queue.then(async () => {
    try {
      await booted;
    } catch {
      post({ type: "result", id: msg.id, ok: false, error: "engine not started" });
      return;
    }
    if (!api) {
      post({ type: "result", id: msg.id, ok: false, error: "engine not available" });
      return;
    }
    await handle(msg);
  });
};
