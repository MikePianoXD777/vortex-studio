#!/usr/bin/env bash
# Arma el .tar.gz de Linux a partir de lo que dejó PyInstaller en dist/.
#
# Uso: empaquetado/linux/empaquetar.sh [versión]
# Sin versión la toma de vortex_studio/__init__.py.
set -euo pipefail

raiz="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$raiz"

version="${1:-$(sed -n 's/^__version__ = "\(.*\)"/\1/p' src/vortex_studio/__init__.py)}"
nombre="VortexStudio-$version-linux-x86_64"
armado="dist/$nombre"

if [ ! -x dist/vortex-studio/vortex-studio ]; then
    echo "Primero compila: ./construir.sh" >&2
    exit 1
fi

rm -rf "$armado" "dist/$nombre.tar.gz"
mkdir -p "$armado/iconos"
cp -a dist/vortex-studio "$armado/vortex-studio"
cp empaquetado/linux/instalar.sh empaquetado/linux/desinstalar.sh \
   empaquetado/linux/vortex-studio.desktop "$armado/"
cp empaquetado/linux/LEEME.txt LICENSE "$armado/"
cp src/vortex_studio/assets/vortex-studio-*.png "$armado/iconos/"
chmod +x "$armado/instalar.sh" "$armado/desinstalar.sh"

tar -C dist -czf "dist/$nombre.tar.gz" "$nombre"
echo "dist/$nombre.tar.gz"
