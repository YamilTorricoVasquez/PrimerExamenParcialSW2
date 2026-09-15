#!/bin/bash
# ---------------------------------------------------------------
# run_app.sh
# Levanta el dashboard del proyecto con un solo comando: ./run_app.sh
# Crea el entorno virtual la primera vez si no existe, instala
# dependencias si hace falta, y luego arranca Streamlit.
# ---------------------------------------------------------------

cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "[1/3] Creando entorno virtual por primera vez..."
    python3 -m venv venv
fi

echo "[2/3] Activando entorno virtual..."
source venv/bin/activate

if ! pip show flask > /dev/null 2>&1; then
    echo "[3/3] Instalando dependencias del proyecto, esto puede tardar unos minutos..."
    pip install -r requirements.txt
else
    echo "[3/3] Dependencias ya instaladas, continuando..."
fi

echo ""
echo "Levantando el servidor... abre http://localhost:5000 en tu navegador."
echo "Para detener el servidor, presiona Ctrl+C."
echo ""

python app.py
