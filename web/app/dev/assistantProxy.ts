// Local stand-in for the site's assistant server (phase C deploys the same contract as a small server).
// The browser engine calls /api/assistant/chat/completions in OpenAI wire format without any key; this proxy adds
// the key and the model from the server's environment, so neither ever reaches the page.
//
//   GET  /api/assistant/info               -> { available, model, upstream, approved }
//   POST /api/assistant/chat/completions   -> forwarded to <upstream>/chat/completions
//
// Environment (process or web/app/.env.local, which git ignores):
//   ASSISTANT_API_KEY      key for the upstream; falls back to MISTRAL_API_KEY, then OPENAI_API_KEY
//   ASSISTANT_API_URL      any OpenAI-compatible base URL (default: Mistral or OpenAI, by the key found)
//   ASSISTANT_MODEL        model id (default: mistral-small-latest / gpt-4.1-mini)
//   ASSISTANT_MODEL_APPROVED=1   the model passed the Romanian test (otherwise a local test approves it)
// Request and response bodies are never logged.
import type { IncomingMessage, ServerResponse } from "node:http";
import { loadEnv, type Plugin } from "vite";

type Config = { key: string; url: string; model: string; upstream: string; approved: boolean };

function resolveConfig(env: Record<string, string | undefined>): Config {
  const mistral = !env.ASSISTANT_API_KEY && !!env.MISTRAL_API_KEY;
  const key = env.ASSISTANT_API_KEY || env.MISTRAL_API_KEY || env.OPENAI_API_KEY || "";
  const url = (env.ASSISTANT_API_URL || (mistral ? "https://api.mistral.ai/v1" : "https://api.openai.com/v1")).replace(/\/$/, "");
  const model = env.ASSISTANT_MODEL || (url.includes("mistral") ? "mistral-small-latest" : "gpt-4.1-mini");
  return { key, url, model, upstream: new URL(url).hostname, approved: env.ASSISTANT_MODEL_APPROVED === "1" };
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
      return send(res, 200, cfg.key ? { available: true, model: cfg.model, upstream: cfg.upstream, approved: cfg.approved }
                                    : { available: false });
    }
    if (path === "/api/assistant/chat/completions" && req.method === "POST") {
      if (!cfg.key) return send(res, 503, { error: { message: "The assistant is not configured on this server." } });
      try {
        const body = JSON.parse(await readBody(req));
        body.model = cfg.model;   // the server decides the model
        delete body.stream;
        const up = await fetch(`${cfg.url}/chat/completions`, {
          method: "POST",
          headers: { "content-type": "application/json", authorization: `Bearer ${cfg.key}` },
          body: JSON.stringify(body),
          signal: AbortSignal.timeout(120_000),
        });
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
