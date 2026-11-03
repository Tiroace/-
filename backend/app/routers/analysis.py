"""分析任务与报告（§5.4：POST /analysis、GET /analysis/{id}、GET /reports）。

对外语义（D5 钉死）：
    POST /analysis    立即返回 task_id + status=pending（已完成预扣）
    前端轮询 GET /analysis/{id}  → pending/running → done|failed
    超过 background_after_seconds（默认 30 秒）仍没结果：background_mode=true，
    前端转「后台处理中，完成后在历史里看」，服务端继续跑，不取消。

额度：预扣 1 次 → 失败退回 / 成功正式扣（§3 主流程）。
去重：同一用户 24 小时内同一组图直接返回旧报告，不扣次数（§4.2）。
"""
from __future__ import annotations

import base64
import collections
import datetime as dt
import hashlib
import json
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Request, UploadFile

from engine.adapters.content_safety import LocalContentSafetyStub

from .. import worker
from ..config import get_settings
from ..deps import current_user, envelope, get_db
from ..errors import AppError, not_found, rate_limited, validation_error
from ..quota import balance, hold_for_analysis

router = APIRouter(tags=["分析/报告"])

_rate_buckets: dict[str, collections.deque] = {}
_TS_FMT = "%Y-%m-%d %H:%M:%S"


def _now() -> str:
    return dt.datetime.now().strftime(_TS_FMT)


def _elapsed_ms(created_at: str) -> int:
    try:
        created = dt.datetime.strptime(created_at, _TS_FMT)
    except (TypeError, ValueError):
        return 0
    return max(0, int((dt.datetime.now() - created).total_seconds() * 1000))


def _check_rate(user_id: str) -> None:
    settings = get_settings()
    bucket = _rate_buckets.setdefault(user_id, collections.deque())
    cutoff = time.time() - 60
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if len(bucket) >= settings.analysis_per_minute:
        raise rate_limited(f"每分钟最多 {settings.analysis_per_minute} 次分析请求")
    bucket.append(time.time())


def _task_detail(conn, task_id: str) -> dict:
    task = conn.execute("SELECT * FROM analysis_tasks WHERE id = ?", (task_id,)).fetchone()
    if task is None:
        raise not_found("任务不存在")
    report_row = conn.execute("SELECT * FROM reports WHERE task_id = ?", (task_id,)).fetchone()
    settings = get_settings()
    elapsed = _elapsed_ms(task["created_at"])
    running = task["status"] in ("pending", "running")
    return {
        "task_id": task["id"],
        "status": task["status"],
        "error_code": task["error_code"],
        "error_message": task["error_message"],
        "duration_ms": task["duration_ms"],
        # 第 2 关取证字段：真实 OCR 耗时、是否并行、识别了几张。
        # 不暴露 trace 全文（里面有内部规则细节），但这三项足以验收 D40 与排障。
        "ocr_ms": task["ocr_ms"] if "ocr_ms" in task.keys() else None,
        "ocr_parallel": bool(task["ocr_parallel"]) if "ocr_parallel" in task.keys() else None,
        "ocr_images": task["ocr_images"] if "ocr_images" in task.keys() else None,
        "model": task["model"],
        "rules_version": task["prompt_version"],
        "pattern_db_version": (json.loads(report_row["report_json"]).get("pattern_db_version") if report_row else None),
        "created_at": task["created_at"],
        "started_at": task["started_at"],
        "finished_at": task["finished_at"],
        "elapsed_ms": elapsed,
        "poll_after_ms": settings.poll_after_ms if running else None,
        "background_mode": bool(running and elapsed > settings.background_after_seconds * 1000),
        "report": json.loads(report_row["report_json"]) if report_row else None,
    }


ALLOWED_SUFFIX = (".png", ".jpg", ".jpeg", ".webp")


def _validate_image_blob(data: bytes, filename: str | None, idx: int, settings) -> str:
    if len(data) > settings.max_image_mb * 1024 * 1024:
        raise validation_error(f"单张图片不能超过 {settings.max_image_mb}MB")
    suffix = (Path(filename or f"image-{idx}.png").suffix or ".png").lower()
    if suffix not in ALLOWED_SUFFIX:
        raise validation_error(f"不支持的图片格式：{suffix}")
    return suffix


def _load_uploads(conn, user_id: str, image_ids: list[str]) -> list[tuple[str, bytes]]:
    blobs: list[tuple[str, bytes]] = []
    for iid in image_ids:
        row = conn.execute("SELECT * FROM uploads WHERE id = ?", (iid,)).fetchone()
        if row is None or row["user_id"] != user_id:
            # 他人图片与不存在图片一律 400，不暴露存在性（引用无效属于请求参数问题）
            raise AppError("IMAGE_NOT_FOUND", "图片不存在或已过期，请重新上传", 400)
        if row["expires_at"] <= _now():
            raise AppError("IMAGE_EXPIRED", "图片已过期，请重新上传", 400)
        path = Path(row["path"])
        if not path.is_file():
            raise AppError("IMAGE_NOT_FOUND", "图片不存在或已过期，请重新上传", 404)
        blobs.append((path.suffix.lower(), path.read_bytes()))
    return blobs


@router.post("/analysis/upload")
def upload_image(request: Request, image: UploadFile = File(...), user: dict = Depends(current_user)) -> dict:
    """上传单张截图，返回 image_id（D9）。

    这是内容安全的**第一道闸**：超限/可疑图片在这里就拦掉，不扣次数、不建任务；
    第二道闸在分析链路内（引擎的内容安全适配器）。
    """
    settings = get_settings()
    data = image.file.read()
    return _store_image(request, user, data, image.filename, image.content_type, settings)


def _store_image(request: Request, user: dict, data: bytes, filename_hint, content_type, settings) -> dict:
    """multipart 与 base64 两个上传端点共用：校验 → 落盘 → 内容安全第一道闸 → 记 uploads。"""
    suffix = _validate_image_blob(data, filename_hint, 0, settings)
    digest = hashlib.sha256(data).hexdigest()
    image_id = "i_" + uuid.uuid4().hex[:16]
    target = settings.upload_dir / "images" / f"{image_id}{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)

    safety = LocalContentSafetyStub(max_files=1, max_mb=settings.max_image_mb).check([target])
    if not safety.passed:
        target.unlink(missing_ok=True)
        raise AppError("CONTENT_BLOCKED", f"图片未通过内容安全检测：{safety.reason}", 422)

    expires_at = (dt.datetime.now() + dt.timedelta(hours=settings.upload_ttl_hours)).strftime(_TS_FMT)
    with get_db(settings).transaction() as conn:
        conn.execute(
            "INSERT INTO uploads (id, user_id, file_hash, path, size, content_type, expires_at, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (image_id, user["id"], digest, str(target), len(data), content_type, expires_at, _now()),
        )
    return envelope(
        {
            "image_id": image_id,
            "hash": digest,
            "size": len(data),
            "expires_at": expires_at,
            "safety": {"passed": True, "mode": safety.code, "note": safety.reason},
        },
        request,
    )


@router.post("/analysis/upload-base64")
async def upload_image_base64(request: Request, user: dict = Depends(current_user)) -> dict:
    """上传单张截图（base64 JSON），返回 image_id。

    为什么有这一条：微信云托管默认关闭公网访问，小程序端只能走 wx.cloud.callContainer，
    而 callContainer 不支持 multipart。所以云端链路用 JSON 传图：
        POST /analysis/upload-base64  {"image_b64": "...", "mime": "image/jpeg"}
    旧的 multipart 端点保留不删——本地开发、以后开公网仍然用它。

    前端上传前已压到 ≤200KB、边长 ≤1080；这里仍按 max_image_mb 校验，
    防绕过前端直接调接口。两条通道共用 _store_image，内容安全与落盘逻辑完全一致。
    """
    settings = get_settings()
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise validation_error('请求体必须是 JSON：{"image_b64": "...", "mime": "image/jpeg"}') from exc
    if not isinstance(body, dict):
        raise validation_error("请求体必须是 JSON 对象")

    raw = body.get("image_b64") or body.get("imageBase64") or ""
    if not isinstance(raw, str) or not raw.strip():
        raise validation_error("缺少 image_b64")
    mime = str(body.get("mime") or "").lower()
    # 兼容 data URI 前缀：data:image/jpeg;base64,xxxx
    if raw.startswith("data:"):
        header, _, raw = raw.partition(",")
        if not mime and ";" in header:
            mime = header[5:].split(";")[0].lower()
    try:
        data = base64.b64decode(raw, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise validation_error("image_b64 不是合法的 base64") from exc
    if not data:
        raise validation_error("图片内容为空")

    # 有 mime 就用它定扩展名；没有就交给 _validate_image_blob 按默认 png 处理
    suffix_hint = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
    }.get(mime)
    return _store_image(request, user, data, suffix_hint, mime or "image/png", settings)


@router.post("/analysis")
async def create_analysis(request: Request, user: dict = Depends(current_user)) -> dict:
    """创建分析任务：立即返回（status=pending），分析在后台线程池跑。

    两种入参：
    - 推荐（D9）：JSON `{"image_ids":["i_...",...], "idempotency_key":"..."}`
    - 兼容旧调用：multipart（`files[]` + `ocr_text`）
    原型期旁路：JSON 里可直接给 `ocr_text`（正式版删除）。
    """
    settings = get_settings()
    user_id = user["id"]
    db = get_db(settings)
    _check_rate(user_id)

    ctype = (request.headers.get("content-type") or "").lower()
    ocr_text = ""
    idem = request.headers.get("Idempotency-Key") or ""
    blobs: list[tuple[str, bytes]] = []

    with db.connect() as conn:
        if ctype.startswith("multipart/form-data") or ctype.startswith("application/x-www-form-urlencoded"):
            form = await request.form()
            ocr_text = str(form.get("ocr_text") or "")
            uploads = form.getlist("files") or form.getlist("image")
            if len(uploads) > settings.max_images:
                raise validation_error(f"最多上传 {settings.max_images} 张截图")
            for idx, upload in enumerate(uploads):
                data = await upload.read()
                suffix = _validate_image_blob(data, getattr(upload, "filename", None), idx, settings)
                blobs.append((suffix, data))
        else:
            try:
                body = await request.json()
            except Exception as exc:  # noqa: BLE001
                raise validation_error('请求体必须是 JSON：{"image_ids":["i_..."]}') from exc
            if not isinstance(body, dict):
                raise validation_error("请求体必须是 JSON 对象")
            image_ids = [str(x) for x in (body.get("image_ids") or [])]
            ocr_text = str(body.get("ocr_text") or "")
            idem = str(body.get("idempotency_key") or idem or "")
            if len(image_ids) > settings.max_images:
                raise validation_error(f"最多上传 {settings.max_images} 张截图")
            blobs = _load_uploads(conn, user_id, image_ids)

        if not blobs and not ocr_text.strip():
            raise validation_error("至少上传 1 张截图（原型期也可用 ocr_text 走文本旁路）")

        image_hashes = [hashlib.sha256(data).hexdigest() for _, data in blobs]
        hashes_json = json.dumps(image_hashes)

        if idem:
            existing = conn.execute(
                "SELECT id FROM analysis_tasks WHERE user_id = ? AND idem_key = ?", (user_id, idem)
            ).fetchone()
            if existing:
                detail = _task_detail(conn, existing["id"])
                detail["idempotent_replay"] = True
                detail["quota"] = {"balance": balance(conn, user_id)}
                return envelope(detail, request)

        if image_hashes:
            since = (dt.datetime.now() - dt.timedelta(hours=24)).strftime(_TS_FMT)
            dup = conn.execute(
                "SELECT id FROM analysis_tasks WHERE user_id = ? AND image_hashes = ? AND status = 'done' AND created_at >= ?"
                " ORDER BY created_at DESC LIMIT 1",
                (user_id, hashes_json, since),
            ).fetchone()
            if dup:
                detail = _task_detail(conn, dup["id"])
                detail["dedupe_hit"] = True
                detail["quota"] = {"balance": balance(conn, user_id)}
                return envelope(detail, request)

    task_id = "t_" + uuid.uuid4().hex[:16]

    # 预扣 + 建任务：同一事务，余额不足直接失败，不留脏任务
    with db.transaction() as conn:
        hold_for_analysis(conn, user_id, task_id)  # 余额不足抛 QUOTA_EXHAUSTED(402)
        conn.execute(
            "INSERT INTO analysis_tasks (id, user_id, idem_key, image_hashes, status, created_at)"
            " VALUES (?, ?, ?, ?, 'pending', ?)",
            (task_id, user_id, idem or None, hashes_json, _now()),
        )

    # 落盘（分析完按 §8 24 小时内删；截图与原型期 OCR 旁路文本都放这里）
    task_dir = settings.upload_dir / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    for idx, (suffix, data) in enumerate(blobs):
        (task_dir / f"{idx}{suffix}").write_bytes(data)
    if ocr_text.strip():
        (task_dir / "ocr.txt").write_text(ocr_text.strip(), encoding="utf-8")
        # 标记来源：调用方显式给了文本（原型期旁路 / 测试），worker 应当直接用它，
        # 不要再对图片跑真实 OCR。第 2 关起真正做到「有图就识别」的同时，
        # 不能把显式传入文本这条路误伤掉。
        (task_dir / "ocr.source").write_text("api", encoding="utf-8")

    worker.submit(task_id)

    with db.connect() as conn:
        detail = _task_detail(conn, task_id)
        detail["quota"] = {"balance": balance(conn, user_id)}
    detail["dedupe_hit"] = False
    detail["idempotent_replay"] = False
    return envelope(detail, request)


@router.get("/analysis/{task_id}")
def get_analysis(task_id: str, request: Request, user: dict = Depends(current_user)) -> dict:
    """轮询任务状态与报告。他人任务返回 404（不暴露任务是否存在）。"""
    with get_db().connect() as conn:
        task = conn.execute("SELECT user_id FROM analysis_tasks WHERE id = ?", (task_id,)).fetchone()
        if task is None or task["user_id"] != user["id"]:
            raise not_found("任务不存在")
        detail = _task_detail(conn, task_id)
        detail["quota"] = {"balance": balance(conn, user["id"])}
    return envelope(detail, request)


@router.get("/reports")
def list_reports(
    request: Request,
    user: dict = Depends(current_user),
    limit: int = 20,
    cursor: str | None = None,
) -> dict:
    limit = max(1, min(limit, 50))
    with get_db().connect() as conn:
        sql = "SELECT * FROM reports WHERE user_id = ? AND expires_at > ?"
        args: list = [user["id"], _now()]
        if cursor:
            sql += " AND created_at < ?"
            args.append(cursor)
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit + 1)
        rows = conn.execute(sql, args).fetchall()
        items = []
        for row in rows[:limit]:
            report = json.loads(row["report_json"])
            items.append(
                {
                    "report_id": row["id"],
                    "task_id": row["task_id"],
                    "overall": report.get("overall"),
                    "summary": report.get("summary"),
                    "finding_count": len(report.get("findings") or []),
                    "created_at": row["created_at"],
                    "expires_at": row["expires_at"],
                }
            )
        next_cursor = rows[limit]["created_at"] if len(rows) > limit else None
        current_balance = balance(conn, user["id"])
    return envelope({"items": items, "next_cursor": next_cursor, "quota": {"balance": current_balance}}, request)
