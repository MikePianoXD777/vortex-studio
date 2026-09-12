#!/usr/bin/env bash
# Compila Vortex Studio. Equivale a Ctrl+Shift+B en VS Code.
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
    echo "No hay entorno virtual. Creándolo…"
    python3 -m venv .venv
    ./.venv/bin/pip install -q -e ".[dev]"
fi

./.venv/bin/pyinstaller vortex-studio.spec --noconfirm --clean
echo
echo "Listo: dist/vortex-studio/vortex-studio"
