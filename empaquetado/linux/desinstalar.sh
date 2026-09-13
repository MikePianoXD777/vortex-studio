#!/usr/bin/env bash
# Quita Vortex Studio: el programa, el comando, la entrada del menú y el ícono.
#
# Tus proyectos, ajustes, presets y autoguardados no se borran: viven en
# otras carpetas, y perderlos por desinstalar sería peor que dejarlos.
set -euo pipefail

datos="${XDG_DATA_HOME:-$HOME/.local/share}"
programa="$HOME/.local/opt/vortex-studio"
menu="$datos/applications"
iconos="$datos/icons/hicolor"

rm -f "$menu/vortex-studio.desktop"
# El comando solo se borra si es nuestro enlace, no un archivo de otra cosa.
if [ -L "$HOME/.local/bin/vortex-studio" ]; then
    rm -f "$HOME/.local/bin/vortex-studio"
fi
rm -f "$iconos"/*/apps/vortex-studio.png
rm -rf "$programa"

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$menu" || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t "$iconos" || true

echo "Vortex Studio se desinstaló. Tus proyectos y ajustes siguen en su lugar."
