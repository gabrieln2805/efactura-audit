"""Prepare the browser spike: build the engine wheel and a 964-invoice upload ZIP next to index.html.

    python web/spike/prepare.py
    python -m http.server 8731 --bind 127.0.0.1 --directory web/spike
    open http://127.0.0.1:8731/  (the page logs timings; window.__spike holds the full result as JSON)
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main() -> None:
    for old in HERE.glob("*.whl"):
        old.unlink()
    subprocess.run([sys.executable, "-m", "pip", "wheel", str(ROOT), "--no-deps", "-q", "-w", str(HERE)], check=True)
    wheel = next(HERE.glob("efactura_audit-*.whl")).name
    (HERE / "manifest.json").write_text(json.dumps({"wheel": wheel}), encoding="utf-8")

    from efactura_audit.synthetic import write_dataset
    with tempfile.TemporaryDirectory() as tmp:
        write_dataset(Path(tmp), seed=7)
        with zipfile.ZipFile(HERE / "upload.zip", "w", zipfile.ZIP_STORED) as z:   # a ZIP of ANAF ZIPs
            for p in sorted((Path(tmp) / "spv_downloads").glob("*.zip")):
                z.write(p, p.name)
    print(f"ready: {wheel} + upload.zip in {HERE}")


if __name__ == "__main__":
    main()
