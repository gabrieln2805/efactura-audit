"""Settings and workspace paths.

Everything lives in one local workspace folder (default ``~/.efactura-audit``, override with
``EFACTURA_HOME``): the DuckDB file, the user's config.toml, the approved-model list and reports.
"""
from __future__ import annotations

import copy
import os
import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def default_settings() -> dict[str, Any]:
    text = resources.files("efactura_audit").joinpath("config_default.toml").read_text(encoding="utf-8")
    return tomllib.loads(text)


@dataclass
class Workspace:
    root: Path
    settings: dict[str, Any] = field(default_factory=dict)

    @property
    def db_path(self) -> Path:
        return self.root / "audit.duckdb"

    @property
    def config_path(self) -> Path:
        return self.root / "config.toml"

    @property
    def approved_models_path(self) -> Path:
        """One list of Romanian-tested models per computer, shared by every workspace."""
        return models_registry_path()

    @property
    def legacy_models_path(self) -> Path:
        """Per-workspace list written by version 0.1.0; still read so earlier test results count."""
        return self.root / "approved_models.json"

    @property
    def reports_dir(self) -> Path:
        d = self.root / "reports"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def section(self, name: str) -> dict[str, Any]:
        return self.settings.get(name, {})


def models_registry_path() -> Path:
    p = os.environ.get("EFACTURA_MODELS") or Path.home() / ".efactura-audit" / "approved_models.json"
    return Path(p).expanduser()


def load_workspace(root: str | os.PathLike | None = None) -> Workspace:
    root_path = Path(root or os.environ.get("EFACTURA_HOME") or Path.home() / ".efactura-audit").expanduser()
    root_path.mkdir(parents=True, exist_ok=True)
    settings = default_settings()
    cfg = root_path / "config.toml"
    if cfg.exists():
        settings = _deep_merge(settings, tomllib.loads(cfg.read_text(encoding="utf-8")))
    return Workspace(root=root_path, settings=settings)
