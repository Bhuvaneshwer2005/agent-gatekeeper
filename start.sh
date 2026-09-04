#!/bin/sh
# Starts the backend API in the background, waits for it to answer, then
# runs the Streamlit dashboard in the foreground so the container's exit
# code follows the dashboard process (the one the host is actually
# health-checking / serving to users).
set -e

cd /app/backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &

for i in $(seq 1 30); do
    if python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" 2>/dev/null; then
        break
    fi
    sleep 1
done

cd /app/frontend
exec python -m streamlit run dashboard.py \
    --server.port "${PORT:-8501}" \
    --server.address 0.0.0.0 \
    --server.headless true
