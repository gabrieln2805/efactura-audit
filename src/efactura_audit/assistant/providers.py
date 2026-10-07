"""Model providers behind one interface.

Internal message format (provider-neutral):
  {"role": "user", "content": str}
  {"role": "assistant", "content": str, "tool_calls": [{"id": str, "name": str, "arguments": dict}]}
  {"role": "tool", "tool_call_id": str, "name": str, "content": str}

`ollama` runs locally and is the default. `anthropic`, `openai` and `mistral` are cloud providers
used only when the client enables them with their own API key.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

CLOUD_PROVIDERS = {"anthropic", "openai", "mistral"}

# Suggestions only: model names change often, so confirm current IDs in each provider's docs.
SUGGESTED_MODELS = {
    "ollama": ["qwen3:8b", "qwen2.5:7b", "llama3.1:8b", "mistral-nemo"],
    "anthropic": ["claude-sonnet-4-5", "claude-haiku-4-5"],
    "openai": ["gpt-4.1-mini", "gpt-4o-mini"],
    "mistral": ["mistral-large-latest", "mistral-small-latest"],
}


class ProviderError(RuntimeError):
    pass


_THINK = re.compile(r"<(think|thinking|reasoning)>.*?</\1>", re.S | re.I)


def strip_reasoning(text: str) -> str:
    """Remove chain-of-thought blocks some local models (e.g. Qwen3, DeepSeek-R1) put in the answer.

    Handles closed blocks anywhere and an unclosed or orphan-closed block at the start.
    """
    if not text:
        return ""
    t = _THINK.sub("", text)
    t = re.sub(r"(?is)^\s*<(think|thinking|reasoning)>.*$", "", t) if re.match(r"(?is)^\s*<(think|thinking|reasoning)>", t) else t
    if re.search(r"(?i)</(think|thinking|reasoning)>", t):
        t = re.split(r"(?i)</(?:think|thinking|reasoning)>", t)[-1]
    return t.strip()


@dataclass
class Turn:
    text: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    raw: Any = None

    def __post_init__(self):
        self.text = strip_reasoning(self.text)


class Provider:
    name = "base"
    is_cloud = False

    def __init__(self, model: str, api_key: str = "", base_url: str = "", timeout: float = 120.0):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout

    def chat(self, system: str, messages: list[dict], tools: list[dict]) -> Turn:  # pragma: no cover
        raise NotImplementedError

    def _post(self, url: str, payload: dict, headers: dict | None = None) -> dict:
        try:
            r = httpx.post(url, json=payload, headers=headers or {}, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name}: cannot reach {url} ({exc})") from exc
        if r.status_code >= 400:
            raise ProviderError(f"{self.name}: HTTP {r.status_code} — {r.text[:400]}")
        return r.json()


def _openai_tools(tools: list[dict]) -> list[dict]:
    return [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                              "parameters": t["parameters"]}} for t in tools]


class OllamaProvider(Provider):
    name = "ollama"

    def chat(self, system, messages, tools):
        msgs = [{"role": "system", "content": system}]
        for m in messages:
            if m["role"] == "assistant":
                msgs.append({"role": "assistant", "content": m.get("content", ""),
                             "tool_calls": [{"function": {"name": c["name"], "arguments": c["arguments"]}}
                                            for c in m.get("tool_calls", [])]})
            elif m["role"] == "tool":
                msgs.append({"role": "tool", "content": m["content"], "tool_name": m["name"]})
            else:
                msgs.append({"role": m["role"], "content": m["content"]})
        data = self._post(f"{(self.base_url or 'http://localhost:11434').rstrip('/')}/api/chat", {
            "model": self.model, "messages": msgs, "tools": _openai_tools(tools), "stream": False,
            "options": {"temperature": 0, "num_ctx": 16384},
        })
        msg = data.get("message", {})
        calls = []
        for c in msg.get("tool_calls") or []:
            fn = c.get("function", {})
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            calls.append({"id": uuid.uuid4().hex[:9], "name": fn.get("name", ""), "arguments": args})
        return Turn(text=msg.get("content", "") or "", tool_calls=calls, raw=data)


class OpenAICompatibleProvider(Provider):
    name = "openai"
    is_cloud = True
    default_url = "https://api.openai.com/v1"

    def chat(self, system, messages, tools):
        msgs = [{"role": "system", "content": system}]
        for m in messages:
            if m["role"] == "assistant":
                entry = {"role": "assistant", "content": m.get("content") or ""}
                if m.get("tool_calls"):
                    entry["tool_calls"] = [{"id": c["id"], "type": "function",
                                            "function": {"name": c["name"], "arguments": json.dumps(c["arguments"], ensure_ascii=False)}}
                                           for c in m["tool_calls"]]
                msgs.append(entry)
            elif m["role"] == "tool":
                msgs.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]})
            else:
                msgs.append({"role": m["role"], "content": m["content"]})
        data = self._post(f"{(self.base_url or self.default_url).rstrip('/')}/chat/completions", {
            "model": self.model, "messages": msgs, "tools": _openai_tools(tools), "temperature": 0,
        }, {"Authorization": f"Bearer {self.api_key}"})
        msg = data["choices"][0]["message"]
        calls = []
        for c in msg.get("tool_calls") or []:
            raw = c["function"].get("arguments") or "{}"
            try:
                args = json.loads(raw) if isinstance(raw, str) else raw
            except json.JSONDecodeError:
                args = {}
            calls.append({"id": c.get("id") or uuid.uuid4().hex[:9], "name": c["function"]["name"], "arguments": args})
        return Turn(text=msg.get("content") or "", tool_calls=calls, raw=data)


class MistralProvider(OpenAICompatibleProvider):
    name = "mistral"
    default_url = "https://api.mistral.ai/v1"


class AnthropicProvider(Provider):
    name = "anthropic"
    is_cloud = True

    def chat(self, system, messages, tools):
        msgs: list[dict] = []
        for m in messages:
            if m["role"] == "assistant":
                blocks = [{"type": "text", "text": m["content"]}] if m.get("content") else []
                blocks += [{"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["arguments"]}
                           for c in m.get("tool_calls", [])]
                msgs.append({"role": "assistant", "content": blocks or [{"type": "text", "text": ""}]})
            elif m["role"] == "tool":
                block = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}
                if msgs and msgs[-1]["role"] == "user" and isinstance(msgs[-1]["content"], list):
                    msgs[-1]["content"].append(block)
                else:
                    msgs.append({"role": "user", "content": [block]})
            else:
                msgs.append({"role": "user", "content": m["content"]})
        data = self._post(f"{(self.base_url or 'https://api.anthropic.com').rstrip('/')}/v1/messages", {
            "model": self.model, "system": system, "messages": msgs, "max_tokens": 2000, "temperature": 0,
            "tools": [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools],
        }, {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"})
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        calls = [{"id": b["id"], "name": b["name"], "arguments": b.get("input") or {}}
                 for b in data.get("content", []) if b.get("type") == "tool_use"]
        return Turn(text=text, tool_calls=calls, raw=data)


class ScriptedProvider(Provider):
    """Deterministic provider for tests and demos: a function maps the conversation to a Turn."""
    name = "scripted"

    def __init__(self, script: Callable[[list[dict]], Turn], model: str = "scripted"):
        super().__init__(model)
        self.script = script

    def chat(self, system, messages, tools):
        return self.script(messages)


PROVIDERS = {"ollama": OllamaProvider, "openai": OpenAICompatibleProvider, "mistral": MistralProvider,
             "anthropic": AnthropicProvider}


def make_provider(provider: str, model: str, api_key: str = "", base_url: str = "") -> Provider:
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}; choose one of {', '.join(PROVIDERS)}")
    if provider in CLOUD_PROVIDERS and not api_key:
        raise ValueError(f"{provider} needs the client's own API key")
    return PROVIDERS[provider](model=model, api_key=api_key, base_url=base_url)


def ollama_models(base_url: str = "http://localhost:11434") -> list[str]:
    """Models installed in the local Ollama, or [] if Ollama is not running."""
    try:
        r = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=3)
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:  # noqa: BLE001
        return []
