from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .config import settings
from .db import session_factory
from .health import database_is_available
from .recommendation import ServiceError, estimate_ride, list_demo_riders, profile_for_alias, recommend, record_feedback
from .schemas import FeedbackIn, RecommendationIn, RideEstimateIn

app = FastAPI(title="yoxi AI Demo API", version="0.1.0")
app.state.session_factory = session_factory(settings)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(ServiceError)
async def service_error_handler(_request: Request, exc: ServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "request_id": f"err_{uuid4().hex[:12]}", "retryable": exc.retryable}},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, _exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "INVALID_REQUEST",
                "message": "請確認展示乘客、台北座標與含時區的時間格式。",
                "request_id": f"err_{uuid4().hex[:12]}",
                "retryable": False,
            }
        },
    )


def _session() -> Session:
    factory = app.state.session_factory
    with factory() as session:
        yield session


@app.get("/health/live", tags=["health"])
async def live() -> dict[str, str]:
    """Liveness is process-only and remains available when dependencies fail."""
    return {"status": "ok", "service": "backend"}


@app.get("/health/ready", tags=["health"])
async def ready() -> dict[str, str]:
    """Readiness depends on PostgreSQL, not optional external providers."""
    available, _reason = await database_is_available(settings)
    if available:
        return {"status": "ok", "database": "available"}

    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "DB_UNAVAILABLE",
                "message": "目前無法連線至必要的資料庫服務。",
                "request_id": "phase0-health",
                "retryable": True,
            }
        },
    )


@app.get("/api/v1/demo/riders", tags=["demo"])
def demo_riders() -> dict[str, object]:
    with app.state.session_factory() as session:
        return {"riders": list_demo_riders(session)}


@app.get("/api/v1/demo/riders/{rider_alias}/profile", tags=["demo"])
def demo_profile(rider_alias: str) -> dict[str, object]:
    with app.state.session_factory() as session:
        return profile_for_alias(session, rider_alias)


@app.post("/api/v1/recommendations", tags=["recommendations"])
def recommendations(payload: RecommendationIn) -> dict[str, object]:
    with app.state.session_factory.begin() as session:
        return recommend(
            session,
            payload.rider_alias,
            payload.location.latitude,
            payload.location.longitude,
            payload.datetime,
        )


@app.post("/api/v1/ride/estimate", tags=["ride"])
def ride_estimate(payload: RideEstimateIn) -> dict[str, object]:
    with app.state.session_factory.begin() as session:
        return estimate_ride(
            session,
            payload.request_id,
            payload.place_key,
            payload.origin.latitude,
            payload.origin.longitude,
            payload.destination.latitude,
            payload.destination.longitude,
            payload.datetime,
        )


@app.post("/api/v1/feedback", tags=["feedback"])
def feedback(payload: FeedbackIn) -> dict[str, object]:
    with app.state.session_factory.begin() as session:
        return record_feedback(session, payload.request_id, payload.place_key, payload.action)
