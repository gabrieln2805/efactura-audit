"""Command line: efactura-audit <command> [options]

  demo         generate synthetic invoices, import, audit and score against the ground truth
  import       import ANAF ZIPs / XML files or folders
  audit        run the five checks
  build        rebuild the SQL models (staging, intermediate, marts) and run the data tests
  explore      browse the tables and models in DuckDB's web UI (read-only)
  report       write the Excel and PDF report
  app          open the local web app (Streamlit)
  mcp          run the MCP server (stdio) for MCP clients
  ask          ask the assistant one question
  test-model   run the Romanian task set against a model and record the result
  feedback     mark a flag confirmed / dismissed
  status       show what is in the workspace
  init         write a config.toml to edit
  reset        delete all invoices and flags (keeps feedback)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from .config import load_workspace
from .store import Store

def _version() -> str:
    try:
        from importlib.metadata import version
        return version("efactura-audit")
    except Exception:  # noqa: BLE001 - running from source without an install
        from . import __version__
        return __version__


KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "mistral": "MISTRAL_API_KEY"}


def _ws_store(args):
    ws = load_workspace(args.workspace)
    return ws, Store(ws.db_path)


def cmd_init(args):
    ws = load_workspace(args.workspace)
    if ws.config_path.exists() and not args.force:
        print(f"{ws.config_path} already exists (use --force to overwrite)")
        return
    from importlib import resources
    text = resources.files("efactura_audit").joinpath("config_default.toml").read_text(encoding="utf-8")
    if args.buyer_cui:
        text = text.replace('buyer_cui = ""', f'buyer_cui = "{args.buyer_cui}"', 1)
    ws.config_path.write_text(text, encoding="utf-8")
    print(f"Wrote {ws.config_path}")


def cmd_import(args):
    from .importer import import_paths
    ws, store = _ws_store(args)
    buyer = args.buyer_cui or ws.section("company").get("buyer_cui", "")
    res = import_paths(store, args.paths, buyer, progress=lambda n: print(f"  … {n} files", end="\r"))
    print(res.summary())
    for e in res.errors[:10]:
        print("  error:", e)
    if args.audit and res.imported:
        cmd_audit(args)
    else:
        _print_data_tests(store.run_data_tests())


def cmd_audit(args):
    from .engine import run_audit
    ws, store = _ws_store(args)
    res = run_audit(store, ws.settings)
    print(res.summary(), f"({res.seconds:.1f}s)")
    _print_data_tests(res.data_tests)


def _print_data_tests(results, show_all: bool = False) -> None:
    issues = [r for r in results if r.status != "pass"]
    print(f"Data tests: {len(results) - len(issues)} passed, {len(issues)} with issues")
    for r in results if show_all else issues:
        detail = f"{r.failures} rows" if r.status in ("warn", "fail") else r.message
        print(f"  {r.status.upper():<5} {r.name}" + (f" ({detail})" if r.status != "pass" else ""))
        if r.status in ("warn", "fail") and r.message:
            print(f"        {r.message}")


def cmd_explore(args):
    """Browse the workspace's tables and models in DuckDB's local web UI, read-only."""
    import time
    import webbrowser

    import duckdb
    ws, _ = _ws_store(args)   # opening the store migrates the workspace and builds the models
    # in-memory main database: the UI caches results in an attached in-memory database, which DuckDB
    # refuses to create from a read-only file connection
    con = duckdb.connect()
    con.execute("INSTALL ui")
    con.execute("ATTACH '{}' AS audit (READ_ONLY)".format(ws.db_path.as_posix().replace("'", "''")))
    con.execute("USE audit")
    msg = con.execute("CALL start_ui_server()").fetchone()[0]
    if "http" not in msg:
        print(f"{msg}. Close the other DuckDB UI first.")
        return
    url = msg[msg.index("http"):].strip()
    print(f"DuckDB UI: {url}  (database 'audit', read-only)", flush=True)
    print("The page is loaded from ui.duckdb.org; queries run on this computer.")
    print("While it is open the app cannot save audits or reviews. Press Ctrl+C here to close it.", flush=True)
    webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        con.execute("CALL stop_ui_server()")
        print("Closed.")


def cmd_build(args):
    from .transform import project
    _, store = _ws_store(args)
    store.build_models(force=True)
    for layer in ("staging", "intermediate", "marts"):
        print(f"{layer:<13} {', '.join(sorted(m.name for m in project().layer(layer)))}")
    _print_data_tests(store.run_data_tests(), show_all=args.verbose)


def cmd_report(args):
    from .report import write_reports
    ws, store = _ws_store(args)
    out = Path(args.out) if args.out else ws.reports_dir
    for p in write_reports(store, out, args.lang, tuple(args.format.split(","))):
        print(p)


def cmd_demo(args):
    from .engine import run_audit
    from .evaluate import evaluate
    from .importer import import_paths
    from .synthetic import write_dataset
    ws, store = _ws_store(args)
    if store.count_invoices() and not args.force:
        print("The workspace already has invoices. Use a new --workspace for the demo, or --force to replace them.")
        return
    store.reset()
    data = ws.root / "demo_data"
    summary = write_dataset(data, seed=args.seed, scale=args.scale)
    print(f"Generated {summary['invoices']} synthetic invoices ({summary['from']} – {summary['to']}) in {data}")
    res = import_paths(store, [data / "spv_downloads"])
    print(res.summary())
    audit = run_audit(store, ws.settings)
    print(audit.summary(), f"({audit.seconds:.1f}s)")
    print(evaluate(store.flags(include_dismissed=True), data / "ground_truth.json").report())


def cmd_status(args):
    ws, store = _ws_store(args)
    from .assistant.tools import AuditTools
    ov = AuditTools(store, "en").audit_overview()
    print(f"Workspace: {ws.root}")
    print(json.dumps(ov, indent=2, ensure_ascii=False, default=str))
    fb = store.feedback_stats()
    if not fb.empty:
        print("Review feedback per rule:\n" + fb.to_string(index=False))


def cmd_feedback(args):
    _, store = _ws_store(args)
    store.set_feedback(args.flag_id, args.status, args.note or "")
    print(f"{args.flag_id}: {args.status}")


def cmd_reset(args):
    _, store = _ws_store(args)
    if not args.yes:
        print("This deletes all invoices and flags in the workspace (review feedback is kept). Re-run with --yes.")
        return
    store.reset()
    print("Workspace cleared.")


def _provider(args, ws):
    from .assistant.providers import CLOUD_PROVIDERS, make_provider
    key = ""
    if args.provider in CLOUD_PROVIDERS:
        key = os.environ.get(KEY_ENV[args.provider], "")
        if not key:
            sys.exit(f"Set {KEY_ENV[args.provider]} to the client's own API key to use {args.provider}.")
    base = ws.section("assistant").get("ollama_url", "") if args.provider == "ollama" else ""
    return make_provider(args.provider, args.model, key, base)


def cmd_ask(args):
    from .assistant.agent import Assistant
    from .assistant.backends import LocalBackend, MCPBackend
    from .assistant.evaluation import approved_models
    from .assistant.tools import AuditTools
    ws, store = _ws_store(args)
    ok = any(m["provider"] == args.provider and m["model"] == args.model for m in approved_models(ws))
    if not ok and not (args.allow_untested or ws.section("assistant").get("allow_untested_models")):
        sys.exit(f"{args.provider}:{args.model} has not passed the Romanian task set. Run "
                 f"`efactura-audit test-model --provider {args.provider} --model {args.model}` first, or pass --allow-untested.")
    tools = AuditTools(store, lang=args.lang)
    backend = MCPBackend(str(ws.root), args.lang) if args.transport == "mcp" else LocalBackend(tools)
    try:
        ans = Assistant(_provider(args, ws), backend, tools.audit_overview(),
                        int(ws.section("assistant").get("max_tool_rounds", 6))).ask(args.question)
    finally:
        backend.close()
    if ans.error:
        sys.exit(f"Error: {ans.error}")
    print(ans.text)
    print("\n[AI-generated, descriptive only — not tax or accounting advice]")
    if args.trace:
        for t in ans.trace:
            print(f"\n→ {t.name}({json.dumps(t.arguments, ensure_ascii=False)})")
            print(json.dumps(t.result, ensure_ascii=False, default=str)[:1500])


def cmd_test_model(args):
    from .assistant.evaluation import run_model_test, save_result
    ws = load_workspace(args.workspace)
    result = run_model_test(_provider(args, ws), progress=lambda s: print("  " + s))
    save_result(ws, result)
    print(result.summary())
    print(f"Saved to {ws.approved_models_path}")


def free_port(start: int, tries: int = 20) -> int:
    """First port from `start` that nothing on 127.0.0.1 is listening on (an old app may still hold 8501)."""
    import socket
    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    sys.exit(f"Ports {start}-{start + tries - 1} are all in use; stop old copies of the app or pass --port.")


def cmd_app(args):
    ws = load_workspace(args.workspace)
    app = Path(__file__).parent / "app" / "streamlit_app.py"
    env = {**os.environ, "EFACTURA_HOME": str(ws.root)}
    port = free_port(args.port)
    if port != args.port:
        print(f"Port {args.port} is busy (probably an older copy of the app); using {port} instead.")
    cmd = [sys.executable, "-m", "streamlit", "run", str(app), "--server.address", "127.0.0.1",
           "--server.port", str(port), "--browser.gatherUsageStats", "false", "--client.toolbarMode", "minimal",
           "--server.headless", str(args.headless).lower()]
    print(f"Opening http://127.0.0.1:{port}  (workspace: {ws.root})")
    subprocess.run(cmd, env=env, check=False)


def cmd_mcp(args):
    from .mcp_server import build_server
    build_server(args.workspace, args.lang).run("stdio")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="efactura-audit", description="Local anomaly audit for RO e-Factura supplier invoices.")
    p.add_argument("--workspace", "-w", help="Workspace folder (default: $EFACTURA_HOME or ~/.efactura-audit)")
    p.add_argument("--version", action="version", version=_version())
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("init", help="write config.toml")
    s.add_argument("--buyer-cui")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("import", help="import ANAF ZIP/XML files or folders")
    s.add_argument("paths", nargs="+")
    s.add_argument("--buyer-cui", help="only import invoices issued to this CUI")
    s.add_argument("--audit", action="store_true", help="run the audit after importing")
    s.set_defaults(fn=cmd_import)

    s = sub.add_parser("audit", help="run the anomaly checks")
    s.set_defaults(fn=cmd_audit)

    s = sub.add_parser("build", help="rebuild the SQL models and run the data tests")
    s.add_argument("--verbose", "-v", action="store_true", help="list passing tests too")
    s.set_defaults(fn=cmd_build)

    s = sub.add_parser("explore", help="browse the tables and models in DuckDB's web UI (read-only)")
    s.set_defaults(fn=cmd_explore)

    s = sub.add_parser("report", help="write Excel/PDF report")
    s.add_argument("--lang", choices=["ro", "en"], default="ro")
    s.add_argument("--format", default="xlsx,pdf")
    s.add_argument("--out")
    s.set_defaults(fn=cmd_report)

    s = sub.add_parser("demo", help="synthetic data end to end")
    s.add_argument("--seed", type=int, default=7)
    s.add_argument("--scale", type=float, default=1.0, help="volume multiplier (1 ≈ 950 invoices over 18 months)")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_demo)

    s = sub.add_parser("status", help="workspace overview")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("feedback", help="review a flag")
    s.add_argument("flag_id")
    s.add_argument("status", choices=["open", "confirmed", "dismissed"])
    s.add_argument("--note")
    s.set_defaults(fn=cmd_feedback)

    s = sub.add_parser("reset", help="delete invoices and flags")
    s.add_argument("--yes", action="store_true")
    s.set_defaults(fn=cmd_reset)

    for name, fn, helptext in (("ask", cmd_ask, "ask the assistant"), ("test-model", cmd_test_model, "run the Romanian task set")):
        s = sub.add_parser(name, help=helptext)
        if name == "ask":
            s.add_argument("question")
            s.add_argument("--lang", choices=["ro", "en"], default="ro")
            s.add_argument("--transport", choices=["local", "mcp"], default="local")
            s.add_argument("--trace", action="store_true", help="print tool calls and results")
            s.add_argument("--allow-untested", action="store_true")
        s.add_argument("--provider", default="ollama", choices=["ollama", "anthropic", "openai", "mistral"])
        s.add_argument("--model", required=True)
        s.set_defaults(fn=fn)

    s = sub.add_parser("app", help="open the web app")
    s.add_argument("--port", type=int, default=8501)
    s.add_argument("--headless", action="store_true")
    s.set_defaults(fn=cmd_app)

    s = sub.add_parser("mcp", help="run the MCP server over stdio")
    s.add_argument("--lang", choices=["ro", "en"], default="ro")
    s.set_defaults(fn=cmd_mcp)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
