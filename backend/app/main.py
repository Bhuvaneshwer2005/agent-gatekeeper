# Entry point for the Agent Gatekeeper backend.
# This is a placeholder — routes and wiring get added as each module
# (mandate validator, upsell engine, audit log, panels) is built.

from fastapi import FastAPI

app = FastAPI(title="Agent Gatekeeper")


@app.get("/health")
def health_check():
    # Simple liveness check so the scaffold has something to run and verify.
    return {"status": "ok"}
