import json

import httpx
import pytest

from efactura_audit.assistant.agent import Assistant
from efactura_audit.assistant.backends import LocalBackend, MCPBackend
from efactura_audit.assistant.evaluation import detect_language, parse_numbers, run_model_test
from efactura_audit.assistant.privacy import Redactor
from efactura_audit.assistant.providers import (AnthropicProvider, MistralProvider, OllamaProvider,
                                                OpenAICompatibleProvider, ScriptedProvider, Turn, make_provider)
from efactura_audit.assistant.tools import AuditTools
from oracle import careless_provider, oracle_provider

TOOLS = [{"name": "top_suppliers", "description": "d", "parameters": {"type": "object", "properties": {}, "required": []}}]
HISTORY = [
    {"role": "user", "content": "Top?"},
    {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "name": "top_suppliers", "arguments": {"limit": 2}}]},
    {"role": "tool", "tool_call_id": "c1", "name": "top_suppliers", "content": "{\"x\": 1}"},
]


def test_tools_answer_from_sql(demo):
    t = AuditTools(demo["store"], "ro")
    ov = t.audit_overview()
    assert ov["invoices"] == demo["summary"]["invoices"] and ov["flags_total"] > 0
    flags = t.list_flags(check="near_duplicate", severity="high")
    assert flags["total_matching"] >= 5
    detail = t.get_flag(flags["flags"][0]["flag_id"])
    assert detail["invoice_numbers"] and "evidence" in detail and "title" in detail
    assert t.search_invoices(supplier="betonex")["total_matching"] > 50
    assert t.get_invoice(flags["flags"][0]["invoice_numbers"][0])["invoices"][0]["lines"]
    assert t.supplier_summary("petrodrum")["suppliers"][0]["bank_accounts"][0]["supplier_iban"].count("*") > 8
    assert t.price_changes()["suppliers_ranked_by_increase"]
    assert t.spend_over_time(granularity="quarter")["series"][0]["period"].startswith("2025-Q")
    assert t.run_sql("SELECT COUNT(*) AS n FROM fct_invoices")["rows"][0]["n"] == ov["invoices"]


@pytest.mark.parametrize("query", ["DROP TABLE invoices", "SELECT 1; DROP TABLE invoices",
                                   "SELECT * FROM read_csv('/etc/passwd')", "SELECT * FROM 'secrets.csv'"])
def test_run_sql_is_read_only(demo, query):
    assert "error" in AuditTools(demo["store"]).run_sql(query)


def test_redactor_masks_and_restores():
    r = Redactor(enabled=True)
    out = r.outgoing({"supplier_name": "Ionescu Mihai Andrei PFA", "iban": "RO49AAAA1B31007593840000",
                      "note": "CNP 1850101123456", "rows": list(range(40))})
    text = json.dumps(out, ensure_ascii=False)
    assert "Ionescu" not in text and "RO49AAAA1B31007593840000" not in text and "1850101123456" not in text
    assert len(out["rows"]) == 26
    assert r.incoming("Furnizor persoană fizică #1 a facturat 3.500 lei") == "Ionescu Mihai Andrei PFA a facturat 3.500 lei"
    assert Redactor(enabled=False).outgoing({"iban": "RO49AAAA1B31007593840000"})["iban"].startswith("RO49AAAA")


def test_agent_loop_traces_tool_calls(demo):
    backend = LocalBackend(AuditTools(demo["store"]))

    def script(msgs):
        if msgs[-1]["role"] == "user":
            return Turn(tool_calls=[{"id": "1", "name": "top_suppliers", "arguments": {"limit": 1}}])
        top = json.loads(msgs[-1]["content"])["suppliers"][0]
        return Turn(text=f"{top['supplier_name']}: {top['spend_ron']}")

    ans = Assistant(ScriptedProvider(script), backend).ask("Cine e primul furnizor?")
    assert ans.error is None and ans.trace[0].name == "top_suppliers"
    assert ans.trace[0].result["suppliers"][0]["supplier_name"] in ans.text


def test_agent_reports_unknown_tools_and_step_limit(demo):
    backend = LocalBackend(AuditTools(demo["store"]))
    loop = ScriptedProvider(lambda m: Turn(tool_calls=[{"id": "x", "name": "nope", "arguments": {}}]))
    ans = Assistant(loop, backend, max_rounds=3).ask("?")
    assert ans.error and ans.trace[0].result == {"error": "Unknown tool nope"}


def test_mcp_backend_matches_local(demo):
    mcp = MCPBackend(str(demo["root"]), "ro")
    try:
        names = {s["name"] for s in mcp.tool_specs()}
        assert {"audit_overview", "list_flags", "get_flag", "run_sql"} <= names
        local = LocalBackend(AuditTools(demo["store"], "ro"))
        assert mcp.call("top_suppliers", {"limit": 3}) == local.call("top_suppliers", {"limit": 3})
        assert mcp.call("list_flags", {"check": "vat"}) == local.call("list_flags", {"check": "vat"})
    finally:
        mcp.close()


class FakeResponse:
    def __init__(self, data):
        self.status_code = 200
        self._data = data
        self.text = json.dumps(data)

    def json(self):
        return self._data


def _capture(monkeypatch, response):
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, payload=json, headers=headers or {})
        return FakeResponse(response)

    monkeypatch.setattr(httpx, "post", fake_post)
    return seen


def test_ollama_adapter(monkeypatch):
    seen = _capture(monkeypatch, {"message": {"content": "", "tool_calls": [
        {"function": {"name": "top_suppliers", "arguments": {"limit": 3}}}]}})
    turn = OllamaProvider("qwen3:8b").chat("sys", HISTORY, TOOLS)
    assert seen["url"].endswith("/api/chat") and seen["payload"]["stream"] is False
    assert seen["payload"]["messages"][0] == {"role": "system", "content": "sys"}
    assert seen["payload"]["messages"][-1]["role"] == "tool"
    assert turn.tool_calls[0]["name"] == "top_suppliers" and turn.tool_calls[0]["arguments"] == {"limit": 3}


@pytest.mark.parametrize("cls,url", [(OpenAICompatibleProvider, "api.openai.com"), (MistralProvider, "api.mistral.ai")])
def test_openai_style_adapters(monkeypatch, cls, url):
    seen = _capture(monkeypatch, {"choices": [{"message": {"content": "Gata", "tool_calls": None}}]})
    turn = cls("m", api_key="k").chat("sys", HISTORY, TOOLS)
    assert url in seen["url"] and seen["headers"]["Authorization"] == "Bearer k"
    msgs = seen["payload"]["messages"]
    assert msgs[2]["tool_calls"][0]["function"]["arguments"] == '{"limit": 2}'
    assert msgs[3] == {"role": "tool", "tool_call_id": "c1", "content": "{\"x\": 1}"}
    assert turn.text == "Gata" and not turn.tool_calls


def test_hosted_adapter_sends_no_key_and_is_redacted(monkeypatch):
    from efactura_audit.assistant.providers import HostedProvider
    seen = _capture(monkeypatch, {"choices": [{"message": {"content": "Gata", "tool_calls": None}}]})
    prov = make_provider("hosted", "gpt-x", base_url="https://clarifact.example/api/assistant")
    assert isinstance(prov, HostedProvider) and prov.is_cloud
    prov.chat("sys", HISTORY, TOOLS)
    assert seen["url"] == "https://clarifact.example/api/assistant/chat/completions"
    assert "Authorization" not in seen["headers"]


def test_anthropic_adapter(monkeypatch):
    seen = _capture(monkeypatch, {"content": [{"type": "text", "text": "Uite"},
                                              {"type": "tool_use", "id": "t9", "name": "get_flag", "input": {"flag_id": "X"}}]})
    turn = AnthropicProvider("claude-x", api_key="k").chat("sys", HISTORY, TOOLS)
    p = seen["payload"]
    assert seen["headers"]["x-api-key"] == "k" and p["system"] == "sys"
    assert p["messages"][1]["content"][0]["type"] == "tool_use"
    assert p["messages"][2]["content"][0] == {"type": "tool_result", "tool_use_id": "c1", "content": "{\"x\": 1}"}
    assert p["tools"][0]["input_schema"]["type"] == "object"
    assert turn.text == "Uite" and turn.tool_calls[0] == {"id": "t9", "name": "get_flag", "arguments": {"flag_id": "X"}}


def test_cloud_providers_need_a_key():
    with pytest.raises(ValueError):
        make_provider("anthropic", "claude-x")
    assert make_provider("ollama", "qwen3:8b").is_cloud is False


def test_number_and_language_parsing():
    assert parse_numbers("3.202.298,34 lei și 964 facturi; 1,234,567.89; 12,5") == [3202298.34, 964.0, 1234567.89, 12.5]
    assert detect_language("Facturile semnalate sunt două.") == "ro"
    assert detect_language("The supplier with the most flags is Betonex.") == "en"


def test_model_test_approves_good_and_rejects_careless(tmp_path):
    good = run_model_test(oracle_provider(), tmp_path / "a")
    assert good.passed, good.summary()
    bad = run_model_test(careless_provider(), tmp_path / "b")
    assert not bad.passed and bad.score < 0.3


def test_reasoning_blocks_are_stripped():
    from efactura_audit.assistant.providers import strip_reasoning
    assert strip_reasoning('<think>let me check</think>\n["A-1"]') == '["A-1"]'
    assert strip_reasoning("<think>never closed") == ""
    assert strip_reasoning("orphan reasoning</think>Răspuns") == "Răspuns"
    assert Turn(text="<think>x</think>Gata").text == "Gata"


def test_approved_models_shared_across_workspaces(tmp_path, monkeypatch):
    from efactura_audit.assistant.evaluation import ModelTestResult, approved_models, save_result
    from efactura_audit.config import load_workspace
    monkeypatch.setenv("EFACTURA_MODELS", str(tmp_path / "models.json"))
    a, b = load_workspace(tmp_path / "client-a"), load_workspace(tmp_path / "client-b")
    save_result(a, ModelTestResult("ollama", "qwen3:8b", "2026-09-30T10:00:00", 0.9, True, True, []))
    assert [m["model"] for m in approved_models(b)] == ["qwen3:8b"]
    # results saved per workspace by version 0.1.0 still count
    (b.root / "approved_models.json").write_text(
        '{"models": [{"provider": "ollama", "model": "llama3.1:8b", "passed": true}]}', encoding="utf-8")
    assert {m["model"] for m in approved_models(b)} == {"qwen3:8b", "llama3.1:8b"}


def test_cli_version(capsys):
    from efactura_audit.cli import main
    with pytest.raises(SystemExit):
        main(["--version"])
    out = capsys.readouterr().out.strip()
    assert out and out[0].isdigit()   # installed version, or 0.0.0+unknown from a bare source tree


def test_model_test_stops_when_the_model_is_unreachable(tmp_path):
    from efactura_audit.assistant.providers import ProviderError, ScriptedProvider

    def offline(messages):
        raise ProviderError("ollama: cannot reach http://localhost:11434/api/chat (connection refused)")

    with pytest.raises(ValueError, match="Nothing was tested: ollama: cannot reach"):
        run_model_test(ScriptedProvider(offline), tmp_path)


def test_model_test_stops_when_the_key_or_model_is_rejected(tmp_path):
    from efactura_audit.assistant.providers import ProviderError, ScriptedProvider

    def rejected(messages):
        raise ProviderError("hosted: HTTP 404 — The model `gpt-old` does not exist")

    with pytest.raises(ValueError, match="HTTP 404"):
        run_model_test(ScriptedProvider(rejected), tmp_path)
