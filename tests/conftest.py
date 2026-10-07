import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from efactura_audit.config import default_settings  # noqa: E402
from efactura_audit.engine import run_audit  # noqa: E402
from efactura_audit.importer import import_paths  # noqa: E402
from efactura_audit.store import Store  # noqa: E402
from efactura_audit.synthetic import write_dataset  # noqa: E402


@pytest.fixture(scope="session")
def demo(tmp_path_factory):
    """Synthetic dataset (seed 7), imported and audited once for the whole session."""
    root = tmp_path_factory.mktemp("demo")
    summary = write_dataset(root, seed=7)
    store = Store(root / "audit.duckdb")
    import_paths(store, [root / "spv_downloads"])
    result = run_audit(store, default_settings())
    return {"root": root, "store": store, "summary": summary, "result": result}
