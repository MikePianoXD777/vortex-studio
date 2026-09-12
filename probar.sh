#!/usr/bin/env bash
# Corre el banco de pruebas. Acepta argumentos de pytest:
#   ./probar.sh                     todo
#   ./probar.sh -v                  con detalle
#   ./probar.sh tests/test_audio.py  solo un archivo
#   ./probar.sh -k keyframe          solo lo que coincida
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
    echo "No hay entorno virtual. Corre primero ./construir.sh"
    exit 1
fi

./.venv/bin/python -m pytest "${@:--q}"
