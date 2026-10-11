// Shared by the Assistant and Settings screens: the site's assistant server, the Romanian model test, and API keys.
import { useEffect, useState } from "react";
import { engine } from "./state";

export const HOSTED = "hosted";

/** What the site's assistant server offers (GET api/assistant/info): the model it uses, whether it passed the
 *  Romanian test, and when unavailable, why (for whoever runs the server, e.g. "Ollama is not running"). */
export type HostedInfo = { available: boolean; model?: string; upstream?: string; approved?: boolean; reason?: string };

let info: Promise<HostedInfo> | null = null;
export function useHostedInfo(): HostedInfo | null {
  const [state, setState] = useState<HostedInfo | null>(null);
  useEffect(() => {
    info ??= fetch("api/assistant/info", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : { available: false }))
      .catch(() => ({ available: false }));
    let live = true;
    info.then((i) => live && setState(i));
    return () => { live = false; };
  }, []);
  return state;
}

/** Keys for cloud providers (developer option): kept in memory for this visit only, never stored. */
export const sessionKeys = new Map<string, string>();

export type TestResult = { passed: boolean; summary: string };

/** Run the Romanian task set against a provider, with live progress lines. */
export function useModelTest(onDone?: (r: TestResult) => void) {
  const [running, setRunning] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const [result, setResult] = useState<TestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = async (provider: string, model: string, apiKey = "") => {
    setLog([]);
    setResult(null);
    setError(null);
    setRunning(true);
    try {
      const r = await engine.call<TestResult>("model_test", { provider, model, api_key: apiKey }, undefined,
                                              (line) => setLog((l) => [...l.slice(-30), line]));
      setResult(r);
      onDone?.(r);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  };
  return { run, running, log, result, error };
}
