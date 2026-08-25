"""应用组装入口。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from app.core.config import get_settings, reset_settings_cache
from app.core.logging import setup_logging
from app.core.middleware import RequestIDMiddleware, SecurityHeadersMiddleware
from app.core.errors import AppError
from app.db import init_engine, init_db
from app.providers.singleton import create_provider
from app.routers import patient, doctor
from app.services.consult import (ConsultationService,
                                 ConsultSessionStore,
                                 SessionSweeper)
from app.services.cleanup import CleanupWorker

logger = logging.getLogger(__name__)

_DEV_PLACEHOLDER = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>候诊闻语</title></head>
<body style="font-family:sans-serif;text-align:center;padding-top:3em">
<h1>候诊闻语 · 后端运行中</h1>
<p>前端构建产物缺失，请先执行 web 目录下的 npm run build，
详见部署手册。</p>
<p><a href="/api/health">健康检查</a> |
<a href="/doctor/login">医生端登录页（需前端产物）</a></p>
</body></html>"""


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)
    init_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from app.db import get_engine
        init_db(get_engine(), settings)
        provider = create_provider(settings)
        store = ConsultSessionStore(
            ttl_minutes=settings.session_ttl_minutes,
            max_per_ip=settings.session_max_per_ip,
            max_total=settings.session_max_total,
            daily_reset_at=settings.cleanup_at,
        )
        service = ConsultationService(provider, store, settings)
        from app.core.ratelimit import SlidingWindowRateLimiter
        from app.core.security import LoginLockout, SessionStore
        app.state.provider = provider
        app.state.service = service
        app.state.patient_limiter = SlidingWindowRateLimiter(
            *settings.parsed_patient_rate_limit())
        app.state.patient_limiter_hour = SlidingWindowRateLimiter(1200, 3600)
        app.state.settings = settings
        app.state.login_limiter = SlidingWindowRateLimiter(10, 60)
        app.state.session_store = store
        app.state.login_lockout = LoginLockout(
            settings.login_max_fails, settings.lockout_seconds)
        app.state.doctor_sessions = SessionStore(
            ttl_minutes=settings.session_ttl_minutes)
        cleanup = CleanupWorker(settings)
        cleanup.start()
        sweeper = SessionSweeper(store)
        sweeper.start()
        app.state.cleanup_worker = cleanup
        yield
        cleanup.stop()
        sweeper.stop()
        await provider.aclose()

    app = FastAPI(title="候诊闻语", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIDMiddleware)

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        from app.core.logging import get_request_id
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": exc.message,
                     "trace_id": get_request_id()},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc):
        from app.core.logging import get_request_id
        return JSONResponse(
            status_code=400,
            content={"code": "PARAM_INVALID",
                     "message": "填的内容格式好像不对，请检查一下再试",
                     "trace_id": get_request_id()},
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        from app.core.logging import get_request_id
        logger.exception("未处理异常 path=%s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={"code": "INTERNAL_ERROR",
                     "message": "系统有点小问题，请稍后再试",
                     "trace_id": get_request_id()},
        )

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    app.include_router(patient.router)
    app.include_router(doctor.router)

    dist = Path(__file__).resolve().parent.parent.parent / "web" / "dist"
    if (dist / "index.html").exists():
        from fastapi.staticfiles import StaticFiles
        app.mount("/assets", StaticFiles(directory=dist / "assets"),
                  name="assets")
        index_file = dist / "index.html"

        @app.api_route("/favicon.ico", methods=["GET", "HEAD"])
        async def favicon():
            # 内联 SVG 图标，无文件依赖（防 500）
            return HTMLResponse(
                "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
                "<rect width='32' height='32' rx='7' fill='#0f6b3f'/>"
                "<text x='16' y='22' font-size='16' text-anchor='middle' "
                "fill='#fff'>闻</text></svg>",
                media_type="image/svg+xml")

        @app.api_route("/{full_path:path}", methods=["GET", "HEAD"])
        async def spa(full_path: str):
            # 防目录穿越/绝对路径注入：解析后必须仍位于 dist 内（评审 R1）
            candidate = (dist / full_path).resolve()
            if (full_path
                    and candidate.is_file()
                    and candidate.is_relative_to(dist.resolve())):
                return FileResponse(candidate)
            return FileResponse(index_file)
    else:
        @app.get("/")
        async def dev_root():
            return HTMLResponse(_DEV_PLACEHOLDER)

    return app

