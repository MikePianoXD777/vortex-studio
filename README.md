# Vortex Studio

Editor de video no lineal. Parte de Vortex Suite.

## Arranque

```bash
python -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python -m vortex_studio
```

En VS Code: abre esta carpeta y presiona `F5` (configuración "Vortex Studio").

## Estructura

- `model/` — proyecto, secuencia, pistas, clips. Python puro, sin Qt.
- `media/` — decodificación de video con PyAV. Opcional: sin PyAV la app arranca igual.
- `ui/` — ventana, preview, timeline, transporte.
