#!/usr/bin/env bash
# Instala Vortex Studio para tu usuario y lo agrega al menú de aplicaciones.
#
# No pide contraseña ni toca el sistema: todo va dentro de tu carpeta personal.
#   el programa   ~/.local/opt/vortex-studio/
#   el comando    ~/.local/bin/vortex-studio
#   el menú       ~/.local/share/applications/vortex-studio.desktop
#   el ícono      ~/.local/share/icons/hicolor/<tamaño>/apps/vortex-studio.png
#
# Volver a correrlo actualiza la instalación. Para quitarlo:
#   ~/.local/opt/vortex-studio/desinstalar.sh
set -euo pipefail

aqui="$(cd "$(dirname "$0")" && pwd)"
datos="${XDG_DATA_HOME:-$HOME/.local/share}"
programa="$HOME/.local/opt/vortex-studio"
comandos="$HOME/.local/bin"
menu="$datos/applications"
iconos="$datos/icons/hicolor"

if [ ! -x "$aqui/vortex-studio/vortex-studio" ]; then
    echo "No encuentro el programa en $aqui/vortex-studio/." >&2
    echo "Corre este script desde la carpeta que salió del .tar.gz." >&2
    exit 1
fi

# Si el paquete está dentro de la carpeta destino, borrarla se llevaría el
# propio instalador y no quedaría nada que copiar.
case "$aqui/" in
    "$programa"/*)
        echo "Estás corriendo el instalador desde dentro de $programa." >&2
        echo "Descomprime el .tar.gz en otro lado (por ejemplo ~/Descargas) y córrelo desde ahí." >&2
        exit 1
        ;;
esac

echo "Instalando Vortex Studio en $programa…"
# Se reemplaza la carpeta completa: así una actualización no deja bibliotecas
# viejas mezcladas con las nuevas. Los proyectos, ajustes y autoguardados
# viven en otras carpetas y no se tocan.
rm -rf "$programa"
mkdir -p "$programa" "$comandos" "$menu"
cp -a "$aqui/vortex-studio/." "$programa/"
cp "$aqui/desinstalar.sh" "$programa/desinstalar.sh"
chmod +x "$programa/desinstalar.sh" "$programa/vortex-studio"

ln -sfn "$programa/vortex-studio" "$comandos/vortex-studio"

for archivo in "$aqui"/iconos/vortex-studio-*.png; do
    [ -e "$archivo" ] || continue
    lado="$(basename "$archivo" .png)"
    lado="${lado##*-}"
    mkdir -p "$iconos/${lado}x${lado}/apps"
    cp "$archivo" "$iconos/${lado}x${lado}/apps/vortex-studio.png"
done

# La ruta del programa se escribe en la entrada del menú; con una ruta
# relativa el menú no lo encontraría.
# El % se duplica: en un .desktop es el inicio de un código (%U, %f) y una
# ruta con % dejaba la entrada del menú sin abrir.
escapada="$(printf '%s' "$programa/vortex-studio" | sed 's/%/%%/g; s/[\/&|]/\\&/g')"
sed "s|@EXEC@|$escapada|g" "$aqui/vortex-studio.desktop" > "$menu/vortex-studio.desktop"
chmod 644 "$menu/vortex-studio.desktop"

# Que el menú se entere sin cerrar sesión. Si las herramientas no están, el
# menú lo nota solo en unos segundos.
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$menu" || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t "$iconos" || true

echo "Listo. Búscalo como «Vortex Studio» en tu menú de aplicaciones."
case ":$PATH:" in
    *":$comandos:"*) echo "También puedes abrirlo con el comando: vortex-studio" ;;
    *) echo "Para abrirlo desde la terminal, agrega $comandos a tu PATH." ;;
esac
