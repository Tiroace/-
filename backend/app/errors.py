"""统一错误码。前端 mock 与后端实现都按这张表来，不要各写一套。"""


class AppError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400, detail: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.detail = detail or {}


# 400
def validation_error(message: str, detail: dict | None = None) -> AppError:
    return AppError("VALIDATION_ERROR", message, 400, detail)


# 401
def unauthorized(message: str = "未登录或登录已过期") -> AppError:
    return AppError("UNAUTHORIZED", message, 401)


# 403（越权看他人报告、非管理员）
def forbidden(message: str = "无权访问该资源") -> AppError:
    return AppError("FORBIDDEN", message, 403)


# 404
def not_found(message: str = "资源不存在") -> AppError:
    return AppError("NOT_FOUND", message, 404)


# 402（次数不足）
def quota_exhausted(balance: int = 0) -> AppError:
    return AppError("QUOTA_EXHAUSTED", "本次免费次数已用完，看广告或开通会员可继续", 402, {"balance": balance})


# 409（同一幂等键参数不一致）
def idempotency_conflict() -> AppError:
    return AppError("IDEMPOTENCY_CONFLICT", "幂等键已被不同的请求使用", 409)


# 422（内容安全拦截）
def content_blocked(reason: str) -> AppError:
    return AppError("CONTENT_BLOCKED", f"图片未通过内容安全检测：{reason}", 422)


# 429
def rate_limited(message: str = "操作太频繁，请稍后再试") -> AppError:
    return AppError("RATE_LIMITED", message, 429)


# 502（模型/分析失败，可退次数）
def analysis_failed(code: str, message: str) -> AppError:
    return AppError(code, message, 502)


# 503（OCR/云服务不可用，可退次数）
def analysis_unavailable(message: str) -> AppError:
    return AppError("ANALYSIS_UNAVAILABLE", message, 503)


# 500
def internal_error(message: str = "服务内部错误") -> AppError:
    return AppError("INTERNAL_ERROR", message, 500)
