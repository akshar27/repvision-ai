from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api.routes import router
from .config import settings
from .tracking.feedback import DISCLAIMER

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="RepVision AI", version="0.1.0",
              description="Pose-based exercise rep counting and movement feedback. " + DISCLAIMER)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.exception_handler(StarletteHTTPException)
async def http_exc(_: Request, exc: StarletteHTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": f"http_{exc.status_code}", "message": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content={"error": detail})


@app.exception_handler(RequestValidationError)
async def validation_exc(_: Request, exc: RequestValidationError):
    msg = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
    return JSONResponse(status_code=422, content={"error": {"code": "validation_error", "message": msg}})
