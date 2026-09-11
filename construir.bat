@echo off
REM Compila Vortex Studio en Windows. Equivale a Ctrl+Shift+B en VS Code.
setlocal

if not exist ".venv\Scripts\python.exe" (
    echo No hay entorno virtual. Creandolo...
    python -m venv .venv || goto :error
    .venv\Scripts\pip install -e ".[dev]" || goto :error
)

.venv\Scripts\pyinstaller vortex-studio.spec --noconfirm --clean || goto :error

echo.
echo Listo: dist\vortex-studio\vortex-studio.exe
goto :eof

:error
echo.
echo Fallo la compilacion.
exit /b 1
