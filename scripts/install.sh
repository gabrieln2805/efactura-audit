#!/usr/bin/env bash
# e-Factura Anomaly Audit — macOS / Linux installer. Run from the project folder: bash scripts/install.sh
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
$PY -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ required"'
$PY -m venv .venv
.venv/bin/python -m pip install --upgrade pip --quiet
.venv/bin/python -m pip install ".[dev]" --quiet
echo
echo "Done."
echo "  Start the app:      .venv/bin/efactura-audit app"
echo "  Try the demo:       .venv/bin/efactura-audit -w ~/efactura-demo demo"
echo "  Run the tests:      .venv/bin/python -m pytest"
