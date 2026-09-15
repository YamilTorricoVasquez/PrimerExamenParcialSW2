@echo off
REM ---------------------------------------------------------------
REM run_app.bat
REM Levanta el dashboard del proyecto con un solo doble clic.
REM Crea el entorno virtual la primera vez si no existe, instala
REM dependencias si hace falta, y luego arranca Streamlit.
REM ---------------------------------------------------------------

cd /d "%~dp0"

if not exist "venv\" (
    echo [1/3] Creando entorno virtual por primera vez...
    python -m venv venv
)

echo [2/3] Activando entorno virtual...
call venv\Scripts\activate.bat

pip show flask >nul 2>&1
if errorlevel 1 (
    echo [3/3] Instalando dependencias del proyecto, esto puede tardar unos minutos...
    pip install -r requirements.txt
) else (
    echo [3/3] Dependencias ya instaladas, continuando...
)

echo.
echo Levantando el servidor... abre http://localhost:5000 en tu navegador.
echo Para detener el servidor, cierra esta ventana o presiona Ctrl+C.
echo.

python app.py

pause
