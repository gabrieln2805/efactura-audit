// Local stand-in for the site's assistant server (phase C deploys the same contract as a small server).
// The browser engine calls /api/assistant/chat/completions in OpenAI wire format without any key; this proxy adds
// the model (and a key, if the upstream needs one) from the server's environment, so nothing reaches the page.
//
//   GET  /api/assistant/info               -> { available, model, upstream, approved, reason? }
//   POST /api/assistant/chat/completions   -> forwarded to <upstream>/chat/completions
//
// Default: an open-source model (Qwen3 8B) served by Ollama on this machine, through Ollama's OpenAI-compatible
// API. Start Ollama with OLLAMA_CONTEXT_LENGTH=16384: its default context is too short for the tool results.
// Any other OpenAI-compatible service (an EU host for open models, vLLM on our own server...) is configured with
// (process environment or web/app/.env.local, which git ignores):
//   ASSISTANT_API_URL      base URL, e.g. http://localhost:11434/v1 (default)
//   ASSISTANT_MODEL        model id (default: qwen3:8b)
//   ASSISTANT_API_KEY      only if the service needs one
//   ASSISTANT_MODEL_APPROVED=1   the model passed the Romanian test (otherwise a local test approves it)
// Request and response bodies are never logged.
import type { IncomingMessage, ServerResponse } from "node:http";
import { loadEnv, type Plugin } from "vite";

type Config = { key: string; url: string; model: string; upstream: string; approved: boolean; ollama: boolean };

const OLLAMA = "http://localhost:11434/v1";

function resolveConfig(env: Record<string, string | undefined>): Config {
  // only the ASSISTANT_* settings count: a provider key that happens to be in the environment is never picked up
  const url = (env.ASSISTANT_API_URL || OLLAMA).replace(/\/$/, "");
  const model = env.ASSISTANT_MODEL || "qwen3:8b";
  const host = new URL(url).hostname;
  return { key: env.ASSISTANT_API_KEY || "", url, model, approved: env.ASSISTANT_MODEL_APPROVED === "1",
           ollama: url === OLLAMA || /:11434$/.test(new URL(url).host),
           upstream: host === "localhost" || host === "127.0.0.1" ? `${host} (Ollama)` : host };
}

/** Is the upstream there, with the model installed? Only checked for Ollama, which is often simply not running. */
async function probe(cfg: Config): Promise<string | null> {
  if (!cfg.ollama) return null;
  try {
    const r = await fetch(`${cfg.url}/models`, { signal: AbortSignal.timeout(2000) });
    const ids: string[] = ((await r.json()).data ?? []).map((m: { id: string }) => m.id);
    return ids.includes(cfg.model) ? null : `Ollama is running but ${cfg.model} is not installed: run "ollama pull ${cfg.model}".`;
  } catch {
    return `Ollama is not running at ${cfg.url.replace(/\/v1$/, "")}. Install it from ollama.com, run "ollama pull ${cfg.model}", then start it.`;
  }
}

function send(res: ServerResponse, status: number, body: unknown) {
  res.statusCode = status;
  res.setHeader("content-type", "application/json");
  res.setHeader("cache-control", "no-store");
  res.end(JSON.stringify(body));
}

async function readBody(req: IncomingMessage, limit = 4 * 1024 * 1024): Promise<string> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > limit) throw new Error("request too large");
    chunks.push(chunk as Buffer);
  }
  return Buffer.concat(chunks).toString("utf-8");
}

export function assistantProxy(): Plugin {
  let cfg: Config;
  const handle = async (req: IncomingMessage, res: ServerResponse, next: () => void) => {
    const path = (req.url ?? "").split("?")[0];
    if (!path.startsWith("/api/assistant")) return next();
    if (path === "/api/assistant/info" && req.method === "GET") {
      const reason = await probe(cfg);
      return send(res, 200, reason ? { available: false, model: cfg.model, upstream: cfg.upstream, reason }
                                   : { available: true, model: cfg.model, upstream: cfg.upstream, approved: cfg.approved });
    }
    if (path === "/api/assistant/chat/completions" && req.method === "POST") {
      try {
        const body = JSON.parse(await readBody(req));
        body.model = cfg.model;   // the server decides the model
        delete body.stream;
        const up = await fetch(`${cfg.url}/chat/completions`, {
          method: "POST",
          headers: { "content-type": "application/json", ...(cfg.key ? { authorization: `Bearer ${cfg.key}` } : {}) },
          body: JSON.stringify(body),
          signal: AbortSignal.timeout(120_000),
        });
        if (up.status === 401 || up.status === 403) {
          // the upstream's message quotes part of the server's key: the page must not see it
          await up.body?.cancel();
          return send(res, up.status, { error: { message:
            `The model provider rejected the assistant server's API key (HTTP ${up.status}). ` +
            "Set a valid ASSISTANT_API_KEY on the server and restart it." } });
        }
        res.statusCode = up.status;
        res.setHeader("content-type", up.headers.get("content-type") ?? "application/json");
        res.setHeader("cache-control", "no-store");
        return res.end(await up.text());
      } catch (e) {
        return send(res, 502, { error: { message: `assistant upstream: ${(e as Error).message}` } });
      }
    }
    return send(res, 404, { error: { message: "not found" } });
  };
  return {
    name: "assistant-proxy",
    configResolved(c) {
      cfg = resolveConfig({ ...loadEnv(c.mode, c.root, ""), ...process.env });
    },
    configureServer(server) {
      server.middlewares.use(handle);
    },
    configurePreviewServer(server) {
      server.middlewares.use(handle);
    },
  };
}
