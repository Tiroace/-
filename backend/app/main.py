"""FastAPI 应用入口。

启动：
    python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
    （在 D:\\qiuzhibilei 下执行；接口文档 http://127.0.0.1:8000/docs）
"""
from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import worker
from .config import get_settings
from .deps import get_db
from .errors import AppError
from .community.sensitive_seed import seed_sensitive_words
from .patterns_seed import seed_patterns
from .routers import ad, admin, analysis, auth, community, feedback, orders, patterns

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("qbl")

app = FastAPI(
    title="面试请等等 · 后端 API（原型）",
    version="0.1.0",
    description="字段级契约见 docs/04-后端接口契约.md；统一响应封套 {ok, data, request_id}。",
)

# CORS：只放本机开发来源（微信开发者工具 / 浏览器调试），绝不开 *
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d{1,5})?$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
)

app.include_router(auth.router)
app.include_router(analysis.router)
app.include_router(ad.router)
app.include_router(orders.router)
app.include_router(feedback.router)
app.include_router(admin.router)
app.include_router(patterns.router)
app.include_router(community.router)
app.include_router(community.admin_router)


@app.middleware("http")
async def community_gate_middleware(request: Request, call_next):
    """D-07：开关关闭时所有 /community/* 一律 404，且在 body 校验之前拦截。"""
    if request.url.path.startswith("/community/") and not get_settings().feature_community:
        request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:16]
        return JSONResponse(
            status_code=404,
            content={
                "ok": False,
                "error": {"code": "NOT_FOUND", "message": "求助广场暂未开放", "detail": {}},
                "request_id": request_id,
            },
            headers={"X-Request-Id": request_id},
        )
    return await call_next(request)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:16]
    response = await call_next(request)
    response.headers["X-Request-Id"] = request.state.request_id
    return response


def _error(status: int, code: str, message: str, request_id: str, detail: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"ok": False, "error": {"code": code, "message": message, "detail": detail or {}}, "request_id": request_id},
    )


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return _error(exc.http_status, exc.code, exc.message, request.state.request_id, exc.detail)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error(400, "VALIDATION_ERROR", "请求参数不合法", request.state.request_id, {"errors": exc.errors()})


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = {401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(
        exc.status_code, "HTTP_ERROR"
    )
    return _error(exc.status_code, code, str(exc.detail), request.state.request_id)


@app.exception_handler(Exception)
async def unexpected_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("未捕获异常 request_id=%s", request.state.request_id)
    return _error(500, "INTERNAL_ERROR", "服务内部错误", request.state.request_id)


@app.get("/health", tags=["运维"])
def health() -> dict:
    return {"ok": True, "data": {"status": "up", "service": "qbl-backend", "version": app.version}}


@app.on_event("startup")
def _startup() -> None:
    get_db().init()
    seeded = seed_patterns(get_db(), get_settings().project_root / "rules" / "patterns_v1.json")
    if seeded:
        logger.info("套路库已灌种子：%d 条", seeded)
    words = seed_sensitive_words(
        get_db(), get_settings().project_root / "rules" / "sensitive_words_v1.json"
    )
    if words:
        logger.info("敏感词已灌种子：%d 条", words)
    logger.info("数据库就绪：%s", get_db().path)


@app.on_event("shutdown")
def _shutdown() -> None:
    worker.shutdown(wait=False)
    logger.info("后台分析线程池已关闭")
