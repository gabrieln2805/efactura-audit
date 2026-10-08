"""The web app's JSON API (efactura_audit.web): same results as the engine, JSON-safe, errors returned not raised."""
import json

import pytest

from efactura_audit.web import Api


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    a = Api(tmp_path_factory.mktemp("web"))
    a.call("load_demo")
    return a


def call(api: Api, method: str, **args):
    out = json.loads(api.call(method, json.dumps(args)))
    assert out["ok"], out.get("error")
    return out["result"]


def test_demo_matches_native_audit(api, demo):
    native = demo["store"].df("SELECT flag_id, severity, score, amount_at_risk_ron FROM fct_flags ORDER BY flag_id")
    flags = sorted(call(api, "flags"), key=lambda f: f["flag_id"])
    assert [f["flag_id"] for f in flags] == native["flag_id"].tolist()
    assert [f["score"] for f in flags] == pytest.approx(native["score"].tolist())
    assert call(api, "status")["open_flags"] == len(native)
    assert isinstance(flags[0]["evidence"], dict) and isinstance(flags[0]["invoice_keys"], list)


def test_overview_matches_streamlit_numbers(api, demo):
    ov = call(api, "overview", lang="en")
    assert not ov["empty"]
    assert ov["overview"]["invoices"] == demo["store"].scalar("SELECT COUNT(*) FROM fct_invoices")
    assert sum(ov["flags_by_check"].values()) == ov["overview"]["flags_total"]
    assert len(ov["top_flags"]) == 10 and ov["monthly"][0]["month"] < ov["monthly"][-1]["month"]


def test_every_screen_method_is_json(api):
    sup = call(api, "suppliers")[0]["supplier_cui"]
    flag = call(api, "flags")[0]
    inv = call(api, "flag_invoices", flag_id=flag["flag_id"])
    assert inv and inv[0]["lines"]["rows"]
    assert call(api, "search_invoices", supplier=sup, flagged_only=False)["total_matching"] > 0
    assert call(api, "get_invoice", number=inv[0]["number"])["invoices"]
    assert call(api, "supplier", cui=sup)["monthly_spend"]
    assert call(api, "import_info")["log"]
    assert any(t["layer"] == "marts" for t in call(api, "catalog"))
    assert call(api, "lineage")["edges"]
    assert call(api, "table_detail", name="fct_invoices")["preview"]["rows"]
    assert call(api, "spend_heatmap")["zmax"] > 0
    cui = call(api, "chart_suppliers")["default"]
    assert call(api, "supplier_invoices", cui=cui)["invoices"]
    items = call(api, "supplier_items", cui=cui)
    if items:
        assert call(api, "item_prices", item_group=items[0]["item_group"])
    assert call(api, "data_tests")["tests"]
    assert call(api, "sql", query="SELECT COUNT(*) AS n FROM fct_flags")["rows"] == [[37]]
    assert "duplicates" in call(api, "settings")["settings"]


def test_feedback_round_trip(api):
    fid = call(api, "flags")[-1]["flag_id"]
    call(api, "set_feedback", flag_id=fid, status="dismissed", note="ok")
    assert fid not in {f["flag_id"] for f in call(api, "flags")}
    assert fid in {f["flag_id"] for f in call(api, "flags", include_dismissed=True)}
    call(api, "set_feedback", flag_id=fid, status="open", note="")


def test_errors_come_back_as_json(api):
    bad = json.loads(api.call("sql", json.dumps({"query": "DROP TABLE flags"})))
    assert not bad["ok"] and "SELECT" in bad["error"]
    assert not json.loads(api.call("_q"))["ok"]
    assert not json.loads(api.call("nope"))["ok"]


def test_report_returns_bytes(api):
    assert api.call("report", json.dumps({"kind": "pdf", "lang": "ro"}))[:5] == b"%PDF-"


def test_assistant_methods(api, monkeypatch, tmp_path):
    monkeypatch.setenv("EFACTURA_MODELS", str(tmp_path / "models.json"))
    opts = call(api, "assistant_options", provider="openai", cloud_enabled=True, allow_untested=True)
    assert opts["providers"][0] == "ollama" and "openai" in opts["providers"]
    assert opts["models"] and not any(m["approved"] for m in opts["models"])
    assert call(api, "assistant_options")["providers"] == ["ollama"]
    assert call(api, "tested_models") == []
    no_key = json.loads(api.call("ask", json.dumps({"provider": "openai", "model": "x", "question": "?"})))
    assert not no_key["ok"] and "API key" in no_key["error"]
