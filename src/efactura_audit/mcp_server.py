"""MCP server exposing the read-only audit tools over stdio.

Run:  efactura-audit mcp   (or: python -m efactura_audit.mcp_server)

Any MCP client can connect — the in-app assistant (transport "mcp"), Claude Desktop, or another
agent. Tools only read the local DuckDB file; nothing is written and nothing leaves the machine.
"""
from __future__ import annotations

import functools
import inspect
import os
import sys
import typing

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .assistant.tools import CHECK_NAMES, AuditTools
from .config import load_workspace
from .store import Store


def build_server(workspace: str | None = None, lang: str | None = None) -> FastMCP:
    ws = load_workspace(workspace)
    tools = AuditTools(Store(ws.db_path), lang=lang or os.environ.get("EFACTURA_LANG", "ro"))
    server = FastMCP("efactura-audit", log_level="WARNING", instructions=(
        "Read-only tools over a local database of Romanian e-Factura supplier invoices and audit flags. "
        "Flags are prompts to check, not conclusions. Amounts are in lei (RON)."))
    for spec in tools.specs():
        fn = spec.fn

        @functools.wraps(fn)
        def wrapper(*args, __fn=fn, **kwargs):
            return __fn(*args, **kwargs)

        # expose the bound method's signature (without `self`), with annotations resolved to real
        # types (tools.py uses postponed annotations), so FastMCP can build the input schema
        hints = typing.get_type_hints(fn)
        sig = inspect.signature(fn)
        params = []
        for n, p in sig.parameters.items():
            ann = hints.get(n, str)
            if n == "check":
                ann = typing.Optional[typing.Literal[tuple(CHECK_NAMES)]]
            elif n == "severity":
                ann = typing.Optional[typing.Literal["high", "medium", "low"]]
            ann = typing.Annotated[ann, Field(description=spec.param_docs.get(n, ""))]
            params.append(p.replace(annotation=ann))
        sig = sig.replace(parameters=params, return_annotation=inspect.Signature.empty)
        hints = {p.name: p.annotation for p in params}
        wrapper.__signature__ = sig
        wrapper.__annotations__ = {n: hints[n] for n in sig.parameters if n in hints}
        del wrapper.__wrapped__
        doc = spec.description
        if spec.param_docs:
            doc += "\n\nArgs:\n" + "\n".join(f"    {k}: {v}" for k, v in spec.param_docs.items())
        server.add_tool(wrapper, name=spec.name, description=doc)
    return server


def main() -> None:
    workspace = sys.argv[1] if len(sys.argv) > 1 else None
    build_server(workspace).run("stdio")


if __name__ == "__main__":
    main()
