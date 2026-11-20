"""Small API wrapper for the offline migration analyzer."""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from migration_guard.analyzer import analyze

app = FastAPI(title="PostgreSQL Migration Safety Gate", version="0.1.0")


class AnalyzeRequest(BaseModel):
    sql: str = Field(min_length=1, max_length=100_000)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "offline-static-analysis"}


@app.post("/analyze")
def analyze_migration(request: AnalyzeRequest) -> dict:
    try:
        return analyze(request.sql).to_dict()
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
