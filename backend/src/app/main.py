from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from .auth.csrf import CSRFMiddleware
from .core.config import settings
from .core.logging import configure_logging
from .core.rate_limit import limiter
from .mailer import configure_default_mailer


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    configure_default_mailer()
    yield


_is_prod = settings.ENV == "prod"
app = FastAPI(
    title="saiife-hub backend",
    version=settings.APP_VERSION,
    docs_url=None if _is_prod else "/api/v1/docs",
    redoc_url=None if _is_prod else "/api/v1/redoc",
    openapi_url=None if _is_prod else "/api/v1/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.APP_URL, settings.MARKETING_URL],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["*", "X-CSRF-Token"],
)
app.add_middleware(CSRFMiddleware)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(_: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"error": {"code": "rate_limited", "message": "Too many requests — slow down."}},
    )


@app.exception_handler(StarletteHTTPException)
async def _http_exc(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        return JSONResponse(status_code=exc.status_code, content={"error": detail})
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": str(detail)}},
    )


@app.exception_handler(RequestValidationError)
async def _validation_exc(_: Request, exc: RequestValidationError) -> JSONResponse:
    details = []
    for e in exc.errors():
        ctx = e.get("ctx")
        if ctx:
            e = {**e, "ctx": {k: str(v) if isinstance(v, Exception) else v for k, v in ctx.items()}}
        e.pop("url", None)
        details.append(e)
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Invalid request body",
                "details": details,
            }
        },
    )


from app.api.v1.auth.router import router as auth_router  # noqa: E402
from app.api.v1.health.router import router as health_router  # noqa: E402

app.include_router(health_router)
app.include_router(auth_router)
