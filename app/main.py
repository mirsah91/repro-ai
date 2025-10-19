from __future__ import annotations

from fastapi import FastAPI

from app.routers import session

app = FastAPI(title="Session Intelligence Service")
app.include_router(session.router)


@app.get("/health", tags=["health"])
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
