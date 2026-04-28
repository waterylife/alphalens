"""FastAPI entry point for the AlphaLens dashboard backend."""

from __future__ import annotations

from dotenv import load_dotenv

# Load env vars (MINIMAX_API_KEY, FUTU_OPEND_*, etc.) from project-root .env
# before any module that reads them at import time.
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.dividend_index import router as dividend_router
from backend.api.hk_tech import router as hktech_router
from backend.api.us_tech import router as ustech_router
from backend.api.portfolio import router as portfolio_router

app = FastAPI(
    title="AlphaLens API",
    description="Backend for dividend index analysis dashboard",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://trade.1234567.com.cn",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dividend_router)
app.include_router(hktech_router)
app.include_router(ustech_router)
app.include_router(portfolio_router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
