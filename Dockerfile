# Single image bundling both the FastAPI backend and the Streamlit dashboard.
# They run as two processes in one container so the dashboard can keep
# reading backend/data/audit_log.db straight off disk, exactly as it does
# in local dev - no code changes, no second service to wire up.
FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
COPY frontend/requirements.txt frontend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt -r frontend/requirements.txt

COPY backend/ backend/
COPY frontend/ frontend/
COPY start.sh start.sh
RUN chmod +x start.sh

ENV PYTHONUNBUFFERED=1
# The backend is only reached from the frontend process inside this
# container, never from the outside world - so it stays on a fixed
# internal port while the dashboard binds to whatever port the host
# assigns.
ENV AGENT_GATEKEEPER_BASE_URL=http://localhost:8000

CMD ["./start.sh"]
