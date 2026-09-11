@echo off
REM Corre el banco de pruebas en Windows.
setlocal
if not exist ".venv\Scripts\python.exe" (
    echo No hay entorno virtual. Corre primero construir.bat
    exit /b 1
)
.venv\Scripts\python -m pytest -q
