"""Romanian model testing: only models that pass are offered in the app.

Models that sound fluent in Romanian can still pick the wrong tool, invent figures or break JSON.
`run_model_test` builds the fixed synthetic dataset, asks each task in ro_taskset.json and scores:
tool use, correct facts (numbers within tolerance / names / invoice numbers), language, valid
JSON for structured tasks, and refusal of tax advice. Results are saved to approved_models.json.
"""
from __future__ import annotations

import json
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Callable

from ..config import Workspace, default_settings
from ..engine import run_audit
from ..importer import import_paths
from ..store import Store
from ..synthetic import write_dataset
from ..utils import strip_diacritics
from .agent import Assistant
from .backends import LocalBackend
from .providers import Provider
from .tools import AuditTools

RO_WORDS = {"si", "este", "sunt", "facturi", "factura", "furnizor", "furnizorul", "furnizori", "din", "pentru", "cu",
            "care", "au", "lei", "semnalare", "semnalari", "total", "nu", "pe", "la", "de", "cel", "mai", "ati", "am"}
EN_WORDS = {"the", "is", "are", "and", "of", "supplier", "suppliers", "invoice", "invoices", "with", "has", "most",
            "flags", "total", "for", "to", "in", "which", "open"}
DECLINE_MARKERS = ["nu pot", "nu ofer", "nu pot oferi", "nu pot da", "consultan", "contabil", "specialist", "expert",
                   "consilier", "cannot", "can't", "not able", "adviser", "advisor", "accountant"]


RO_STEMS = ("factur", "furniz", "semnal", "chelt", "suma", "sume", "preț", "pret", "cresc", "achiz", "trimestr", "lun")
EN_STEMS = ("invoic", "suppl", "flag", "spend", "spent", "price", "increas", "quarter", "month")


def detect_language(text: str) -> str:
    t = strip_diacritics(text.lower())
    words = re.findall(r"[a-z]+", t)
    ro = sum(w in RO_WORDS or w.startswith(RO_STEMS) for w in words) + 3 * len(re.findall(r"[ăâîșțşţ]", text.lower()))
    en = sum(w in EN_WORDS or w.startswith(EN_STEMS) for w in words)
    return "ro" if ro > en else "en"


_NUM = re.compile(r"\d{1,3}(?:[.\s ]\d{3})+(?:,\d+)?|\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?")


def parse_numbers(text: str) -> list[float]:
    """Numbers in Romanian (1.234.567,89) or English (1,234,567.89) format."""
    out = []
    for raw in _NUM.findall(text):
        s = raw.replace(" ", "").replace(" ", "")
        if "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        elif "," in s:
            parts = s.split(",")
            s = s.replace(",", "") if all(len(p) == 3 for p in parts[1:]) and len(parts) > 2 else s.replace(",", ".")
        elif "." in s:
            parts = s.split(".")
            if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) <= 3 and parts[0] != "0"):
                s = s.replace(".", "")   # thousands separators (RO)
        try:
            out.append(float(s))
        except ValueError:
            pass
    return out


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", strip_diacritics(str(s)).lower()).strip()


def name_in(expected: str, answer: str) -> bool:
    """Supplier names match on their distinctive first words (legal suffixes like SRL are optional)."""
    exp = [w for w in _norm(expected).split() if w not in {"srl", "sa", "pfa", "s.r.l."}]
    key = " ".join(exp[:2]) if len(exp) >= 2 else " ".join(exp)
    return key in _norm(answer) or _norm(expected) in _norm(answer)


def number_in(expected: float, answer: str, tolerance: float = 0.005) -> bool:
    return any(abs(n - expected) <= max(1.0, abs(expected) * tolerance) for n in parse_numbers(answer))


def _extract_json(text: str):
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"(\{.*\}|\[.*\])", t, re.S)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                return None
    return None


@dataclass
class TaskResult:
    id: str
    question: str
    answer: str
    tools_called: list[str]
    tool_ok: bool
    content_ok: bool
    language_ok: bool | None
    error: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def score(self) -> float:
        parts = [self.tool_ok, self.content_ok] + ([self.language_ok] if self.language_ok is not None else [])
        return sum(parts) / len(parts)


@dataclass
class ModelTestResult:
    provider: str
    model: str
    tested_at: str
    score: float
    structured_ok: bool
    passed: bool
    tasks: list[TaskResult]

    def summary(self) -> str:
        lines = [f"{self.provider}:{self.model} — score {self.score:.0%}, structured output "
                 f"{'OK' if self.structured_ok else 'FAILED'} → {'APPROVED' if self.passed else 'NOT APPROVED'}"]
        for t in self.tasks:
            flags = f"tool {'✓' if t.tool_ok else '✗'} facts {'✓' if t.content_ok else '✗'}"
            if t.language_ok is not None:
                flags += f" lang {'✓' if t.language_ok else '✗'}"
            lines.append(f"  {t.id:<22} {flags}" + (f"  [{t.error}]" if t.error else ""))
        return "\n".join(lines)


def load_taskset() -> dict:
    text = resources.files("efactura_audit.assistant").joinpath("ro_taskset.json").read_text(encoding="utf-8")
    return json.loads(text)


def build_test_store(root: Path) -> Store:
    write_dataset(root, seed=7)
    store = Store(root / "audit.duckdb")
    import_paths(store, [root / "spv_downloads"])
    run_audit(store, default_settings())
    return store


def _scalar_list(store: Store, sql: str) -> list:
    df = store.df(sql)
    return [] if df.empty else [v for v in df.iloc[:, 0].tolist() if v is not None]


def score_task(task: dict, answer_text: str, tools_called: list[str], store: Store, params: dict) -> tuple[bool, bool, bool | None, list[str]]:
    notes: list[str] = []
    tools_any = task.get("tools_any") or []
    tool_ok = (not tools_any) or any(t in tools_any for t in tools_called)
    content_ok = True
    for exp in task["expect"]:
        kind = exp["type"]
        sql = exp.get("sql", "").format(**params)
        if kind == "numbers":
            for v in _scalar_list(store, sql):
                if not number_in(float(v), answer_text, exp.get("tolerance", 0.005)):
                    content_ok = False
                    notes.append(f"missing number {v:,.2f}")
        elif kind == "strings":
            vals = [str(v) for v in _scalar_list(store, sql)]
            hits = [v for v in vals if (name_in(v, answer_text) if " " in v else v.lower() in answer_text.lower())]
            ok = bool(hits) if exp.get("mode", "all") == "any" else len(hits) == len(vals)
            if not ok:
                content_ok = False
                notes.append(f"expected {'one of' if exp.get('mode') == 'any' else ''} {vals[:5]}")
        elif kind == "json_object":
            data = _extract_json(answer_text)
            if not isinstance(data, dict):
                content_ok = False
                notes.append("not a JSON object")
                continue
            for key, spec in exp["fields"].items():
                expected = _scalar_list(store, spec["sql"])[0]
                got = data.get(key)
                if spec["match"] == "number":
                    ok = isinstance(got, (int, float)) and abs(float(got) - float(expected)) <= max(1, abs(float(expected)) * spec.get("tolerance", 0.005))
                else:
                    ok = isinstance(got, str) and name_in(str(expected), got)
                if not ok:
                    content_ok = False
                    notes.append(f"{key}: expected {expected!r}, got {got!r}")
        elif kind == "json_list":
            data = _extract_json(answer_text)
            vals = {str(v).upper() for v in _scalar_list(store, sql)}
            if not isinstance(data, list):
                content_ok = False
                notes.append("not a JSON list")
                continue
            got = {str(v).upper() for v in data}
            overlap = len(got & vals) / len(vals) if vals else 1.0
            precision = len(got & vals) / len(got) if got else 0.0
            if overlap < exp.get("min_overlap", 0.6) or precision < 0.6:
                content_ok = False
                notes.append(f"overlap {overlap:.0%}, precision {precision:.0%}")
        elif kind == "declines_advice":
            if not any(m in answer_text.lower() for m in DECLINE_MARKERS):
                content_ok = False
                notes.append("did not decline tax advice")
    lang = task.get("lang", "ro")
    language_ok = None if lang == "json" else (bool(answer_text) and detect_language(answer_text) == lang)
    return tool_ok, content_ok, language_ok, notes


def run_model_test(provider: Provider, work_dir: Path | None = None,
                   progress: Callable[[str], None] | None = None) -> ModelTestResult:
    taskset = load_taskset()
    tmp = tempfile.TemporaryDirectory(prefix="efactura-modeltest-") if work_dir is None else None
    root = Path(tmp.name if tmp else work_dir)
    store = build_test_store(root)
    tools = AuditTools(store, lang="ro")
    backend = LocalBackend(tools)
    overview = tools.audit_overview()
    results: list[TaskResult] = []
    for task in taskset["tasks"]:
        params = {k: (_scalar_list(store, v) or [""])[0] for k, v in (task.get("params_sql") or {}).items()}
        question = task["question"].format(**params)
        if progress:
            progress(f"{task['id']}: {question}")
        ans = Assistant(provider, backend, overview).ask(question)
        called = [t.name for t in ans.trace]
        if ans.error and not results and re.search(r"cannot reach|HTTP 4\d\d", ans.error):
            # the model is not there at all (Ollama not running, key rejected, unknown model): scoring 14 identical
            # failures says nothing, so stop with the reason
            if tmp:
                tmp.cleanup()
            raise ValueError(f"Nothing was tested: {ans.error}")
        if ans.error:
            results.append(TaskResult(task["id"], question, "", called, False, False,
                                      None if task.get("lang") == "json" else False, error=ans.error))
            continue
        tool_ok, content_ok, lang_ok, notes = score_task(task, ans.text, called, store, params)
        results.append(TaskResult(task["id"], question, ans.text, called, tool_ok, content_ok, lang_ok, notes=notes))
    score = sum(r.score for r in results) / len(results)
    structured = [r for r in results if r.id.startswith("json_")]
    structured_score = sum(r.content_ok for r in structured) / len(structured) if structured else 1.0
    structured_ok = structured_score >= taskset.get("structured_threshold", 1.0)
    passed = score >= taskset.get("pass_threshold", 0.8) and structured_ok
    if tmp:
        tmp.cleanup()
    return ModelTestResult(provider=provider.name, model=provider.model, tested_at=datetime.now().isoformat(timespec="seconds"),
                           score=round(score, 3), structured_ok=structured_ok, passed=passed, tasks=results)


# ------------------------------------------------------------------------------ approved list
def _read_models(p: Path) -> list[dict]:
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("models", [])
    except (json.JSONDecodeError, OSError):
        return []


def load_approved(ws: Workspace) -> list[dict]:
    """Tested models from the computer-wide list, plus any older per-workspace results (global wins)."""
    merged: dict[tuple[str, str], dict] = {}
    for p in (ws.legacy_models_path, ws.approved_models_path):
        if p == ws.legacy_models_path and p.resolve() == ws.approved_models_path.resolve():
            continue
        for m in _read_models(p):
            merged[(m["provider"], m["model"])] = m
    return list(merged.values())


def save_result(ws: Workspace, result: ModelTestResult) -> None:
    models = [m for m in _read_models(ws.approved_models_path)
              if not (m["provider"] == result.provider and m["model"] == result.model)]
    entry = asdict(result)
    entry["tasks"] = [{**asdict(t), "score": t.score} for t in result.tasks]
    models.append(entry)
    ws.approved_models_path.parent.mkdir(parents=True, exist_ok=True)
    ws.approved_models_path.write_text(json.dumps({"taskset_version": load_taskset()["version"], "models": models},
                                                  ensure_ascii=False, indent=2), encoding="utf-8")


def approved_models(ws: Workspace) -> list[dict]:
    return [m for m in load_approved(ws) if m.get("passed")]
