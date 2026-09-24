#!/usr/bin/env bash
set -e

# Change to the directory containing this script (plat-reader root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================================="
echo " Starting Standalone Cadastral Plat Reader API Service"
echo "=========================================================="

export PLAT_READER_ALLOWED_ORIGINS="${PLAT_READER_ALLOWED_ORIGINS:-*}"
export PYTHONPATH="$SCRIPT_DIR:$SCRIPT_DIR/plat_curves:$PYTHONPATH"
PORT="${PORT:-8000}"

echo "Base Directory: $SCRIPT_DIR"
echo "Port:           $PORT"
echo "CORS Origins:   $PLAT_READER_ALLOWED_ORIGINS"
echo "Widget URL:     http://localhost:$PORT/widget/"
echo "Health Check:   http://localhost:$PORT/health"
echo "=========================================================="

python3 -m uvicorn backend.server:app --host 0.0.0.0 --port "$PORT" --reload
