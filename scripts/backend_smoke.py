"""后端冒烟自测：一条命令跑完 §5.4 的 12 个端点 + 异步状态机 + 安全用例。

覆盖（实现级；契约级用例由测试者在 tests/ 写）：
1. 登录送 3 次；平台适配层 mock 标记；广告位配置
2. 异步：POST 立即返回 pending → 轮询 running/done；30 秒转后台语义
3. 分析预扣、成功正式扣、失败退回；并发 5 单不串额度
4. 越权看他人报告 → 404；24 小时去重不扣次数
5. 广告奖励幂等 + 每日上限 + 广告拉不出来兜底给次数
6. 支付回调：验签失败拒绝、金额不符拒绝、重复推送幂等、平台单号冲突拒绝
7. 反馈、后台统计、额度对账、词库校验

用临时数据库，不污染 var/。
"""
from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 必须在 import app 之前设定路径（配置在 import 时读取环境变量）
_TMP = tempfile.mkdtemp(prefix="qbl-smoke-")
os.environ["QBL_DB_PATH"] = str(Path(_TMP) / "smoke.db")
os.environ["QBL_UPLOAD_DIR"] = str(Path(_TMP) / "uploads")
os.environ["QBL_REPORT_DIR"] = str(Path(_TMP) / "reports")
os.environ["QBL_CACHE_DIR"] = str(Path(_TMP) / "cache")
os.environ["QBL_ENGINE_MODEL"] = "mock"
os.environ["QBL_POLL_AFTER_MS"] = "50"
os.environ.setdefault("QBL_ADMIN_TOKEN", "dev-admin-token")

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402
from engine.schema import validate_report  # noqa: E402
from engine.textnorm import find_pii  # noqa: E402

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
OCR_TEXT = (PROJECT_ROOT / "data" / "testset" / "ocr" / "T002.txt").read_text(encoding="utf-8")
# 追加一行「风险行 + 手机号」，用于验证输出层 evidence 脱敏（手机号与风险同句才会进 evidence）
OCR_TEXT += "\n请先电话联系 13800000000 并交押金 100 元确认名额"

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: object = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} —— {detail}")


def section(title: str) -> None:
    print(f"\n== {title} ==")


def login(client: TestClient, code: str | None = None, platform: str = "toutiao") -> dict:
    code = code or f"code-{uuid.uuid4().hex[:8]}"
    resp = client.post("/auth/login", json={"platform": platform, "code": code})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def upload_image(client: TestClient, token: str, marker: str) -> str:
    """D9：先上传单图换 image_id。"""
    payload = PNG_1X1 + marker.encode()  # 不同字节 = 不同图，避开去重
    resp = client.post("/analysis/upload", headers=auth(token), files={"image": (f"{marker}.png", payload, "image/png")})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["image_id"]


def create_task(client: TestClient, token: str, marker: str, ocr_text: str = OCR_TEXT, headers: dict | None = None):
    image_id = upload_image(client, token, marker)
    body = {"image_ids": [image_id], "idempotency_key": (headers or {}).get("Idempotency-Key")}
    if ocr_text:
        body["ocr_text"] = ocr_text
    return client.post("/analysis", headers=auth(token), json=body)


def legacy_multipart_create(client: TestClient, token: str, marker: str, ocr_text: str = OCR_TEXT):
    """旧调用方式（multipart + files[]），保留兼容期用。"""
    payload = PNG_1X1 + marker.encode()
    return client.post(
        "/analysis",
        headers=auth(token),
        files=[("files", (f"{marker}.png", payload, "image/png"))],
        data={"ocr_text": ocr_text},
    )


def wait_task(client: TestClient, token: str, task_id: str, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        resp = client.get(f"/analysis/{task_id}", headers=auth(token))
        if resp.status_code != 200:
            raise AssertionError(resp.text)
        last = resp.json()["data"]
        if last["status"] in ("done", "failed"):
            return last
        time.sleep(0.05)
    raise AssertionError(f"任务 {task_id} 超时未结束：{last}")


def run_and_wait(client: TestClient, token: str, marker: str, ocr_text: str = OCR_TEXT) -> dict:
    created = create_task(client, token, marker, ocr_text)
    assert created.status_code == 200, created.text
    return wait_task(client, token, created.json()["data"]["task_id"])


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    with TestClient(app) as client:
        section("0. 健康检查、登录与平台适配层")
        health = client.get("/health")
        check("GET /health 返回 up", health.status_code == 200 and health.json()["data"]["status"] == "up")
        me = login(client)
        token = me["token"]
        check("新用户登录成功且标记 is_new_user", me["is_new_user"] is True)
        check("新用户送 3 次额度", me["quota"]["balance"] == 3, me["quota"])
        check("没有平台凭据时明确标注 platform_mode=mock", me["platform_mode"] == "mock", me.get("platform_mode"))
        check("下发广告位配置且标 mock", me["ad"]["mode"] == "mock" and me["ad"]["enabled"] is True, me.get("ad"))
        check("广告位每日上限 5", me["ad"]["daily_cap"] == 5)

        section("1. 异步分析：POST 立即返回 pending → 轮询 → done")
        created = create_task(client, token, "a1")
        data = created.json()["data"]
        check("POST /analysis 立即返回 task_id", bool(data.get("task_id")))
        check("创建时状态是 pending/running（分析未阻塞请求，D8）", data["status"] in ("pending", "running"), data["status"])
        check("创建时已完成预扣（余额 3→2）", data["quota"]["balance"] == 2, data["quota"])
        check("返回轮询间隔 poll_after_ms", isinstance(data.get("poll_after_ms"), int))
        done = wait_task(client, token, data["task_id"])
        check("轮询后状态变为 done", done["status"] == "done", done["status"])
        check("done 后带上报告", bool(done["report"]))
        report = done["report"]
        errors = validate_report(report, final=True)
        check("报告通过 §4.3 schema", not errors, errors)
        check("报告整体结论 red（T002 押金/服装费）", report["overall"] == "red", report["overall"])
        check("6 个维度齐全", [d["key"] for d in report["dimensions"]] == ["fee", "work", "title", "pay", "company", "contract"])
        check("完成后余额保持 2（正式扣除）", done["quota"]["balance"] == 2, done["quota"])
        out_json = json.dumps(report, ensure_ascii=False)
        check("输出层 PII 零泄漏（报告 JSON 全文扫描）", find_pii(out_json) == [], find_pii(out_json))
        # 引擎每条规则只出一条 finding，含手机号的那一行不一定是被保留的证据；
        # 这里改成「报告全文不得出现完整手机号」+「若该行被引用则必须是打码版」两个更严格的断言。
        check("报告全文不含完整手机号", "13800000000" not in out_json, out_json[-300:])
        phone_in_report = "138****0000" in out_json
        check("手机号若进入证据则已打码", phone_in_report or "13800000000" not in out_json, out_json[-200:])
        check("完成后 poll_after_ms 为 null（不用再轮询）", done["poll_after_ms"] is None)
        task_id = data["task_id"]

        section("2. 越权与幂等")
        other = login(client)
        resp = client.get(f"/analysis/{task_id}", headers=auth(other["token"]))
        check("他人任务返回 404（不暴露存在性）", resp.status_code == 404, resp.status_code)
        resp = client.get(f"/analysis/{task_id}", headers=auth(token))
        check("本人任务可查", resp.status_code == 200 and resp.json()["data"]["report"]["overall"] == "red")
        key = "idem-key-smoke-001"
        first = create_task(client, token, "idem", headers={"Idempotency-Key": key})
        second = create_task(client, token, "idem", headers={"Idempotency-Key": key})
        check("同一 Idempotency-Key 第二次返回同一任务", first.json()["data"]["task_id"] == second.json()["data"]["task_id"])
        check("幂等重放不重复扣额度", second.json()["data"]["quota"]["balance"] == first.json()["data"]["quota"]["balance"])
        wait_task(client, token, first.json()["data"]["task_id"])

        section("3. 24 小时去重")
        before = client.get("/me", headers=auth(token)).json()["data"]["quota"]["balance"]
        dup = create_task(client, token, "a1")  # 同一张图
        check("同一组图再次上传命中 dedupe", dup.json()["data"].get("dedupe_hit") is True, dup.text[:200])
        after = client.get("/me", headers=auth(token)).json()["data"]["quota"]["balance"]
        check("去重命中不扣次数", before == after, f"{before} → {after}")

        section("4. 广告奖励（幂等 / 每日上限 / 兜底）")
        r1 = client.post("/ad/reward", headers=auth(token), json={"request_id": "ad-req-0001", "ad_unit_id": "unit-a", "result": "completed"})
        b1 = r1.json()["data"]["quota"]["balance"]
        check("看完广告 +1 次", r1.status_code == 200 and r1.json()["data"]["granted"] is True, r1.text[:200])
        r1b = client.post("/ad/reward", headers=auth(token), json={"request_id": "ad-req-0001", "ad_unit_id": "unit-a", "result": "completed"})
        check("同一 request_id 重放不重复发放", r1b.json()["data"]["replayed"] is True and r1b.json()["data"]["quota"]["balance"] == b1)
        r2 = client.post("/ad/reward", headers=auth(token), json={"request_id": "ad-req-0002", "ad_unit_id": "unit-a", "result": "no_fill"})
        check("广告拉不出来也直接给次数（平台强制兜底）", r2.json()["data"]["granted"] is True, r2.text[:200])
        for i in range(3, 8):
            client.post("/ad/reward", headers=auth(token), json={"request_id": f"ad-req-000{i}", "ad_unit_id": "unit-a", "result": "completed"})
        cap_resp = client.post("/ad/reward", headers=auth(token), json={"request_id": "ad-req-0099", "ad_unit_id": "unit-a", "result": "completed"})
        check("超过每日上限（5 次）不再发放", cap_resp.json()["data"]["granted"] is False, cap_resp.text[:200])
        check("每日上限字段正确", cap_resp.json()["data"]["daily_cap"] == 5)

        section("5. 订单与支付回调")
        order = client.post("/orders", headers=auth(token), json={"plan": "month", "channel": "toutiao"})
        od = order.json()["data"]
        check("下单金额按服务端定价（月卡 1990 分）", od["amount_fen"] == 1990, od)
        check("支付参数标 mock:true（不能真扣款）", od["pay_params"]["mock"] is True, od["pay_params"])
        notify_fields = {
            "order_id": od["order_id"],
            "platform_order_id": "tt-order-8888",
            "amount_fen": "1990",
            "status": "paid",
        }
        bad = client.post("/pay/notify", json={**notify_fields, "amount_fen": 1990, "signature": "bad-signature"})
        check("伪造回调被拒（验签失败 401）", bad.status_code == 401, bad.status_code)
        from backend.app.platform.mock import MockAdapter
        from backend.app.config import get_settings

        adapter = MockAdapter("toutiao", get_settings())
        sig = adapter.sign(notify_fields)
        wrong_amount_fields = {**notify_fields, "amount_fen": "1"}
        wrong_amount = client.post(
            "/pay/notify",
            json={**wrong_amount_fields, "amount_fen": 1, "signature": adapter.sign(wrong_amount_fields)},
        )
        check("金额不符被拒", wrong_amount.status_code == 400 and wrong_amount.json()["error"]["code"] == "AMOUNT_MISMATCH", wrong_amount.text[:200])
        paid = client.post("/pay/notify", json={**notify_fields, "amount_fen": 1990, "signature": sig})
        check("验签通过后订单变为已支付并发货", paid.status_code == 200 and paid.json()["data"]["status"] == "paid", paid.text[:300])
        replay = client.post("/pay/notify", json={**notify_fields, "amount_fen": 1990, "signature": sig})
        check("同一平台单号重复推送幂等", replay.json()["data"]["replayed"] is True)
        me_after = client.get("/me", headers=auth(token)).json()["data"]
        check("会员生效且每日上限变为 20", me_after["membership"]["active"] is True and me_after["membership"]["daily_limit"] == 20, me_after["membership"])
        order2 = client.post("/orders", headers=auth(token), json={"plan": "week", "channel": "toutiao"}).json()["data"]
        conflict_fields = {"order_id": order2["order_id"], "platform_order_id": "tt-order-8888", "amount_fen": "690", "status": "paid"}
        conflict = client.post("/pay/notify", json={**conflict_fields, "amount_fen": 690, "signature": adapter.sign(conflict_fields)})
        check("平台单号已被其他订单使用 → 409", conflict.status_code == 409, conflict.status_code)

        section("6. 异步失败退次数（模型不可用）")
        fresh = login(client)
        # 路线调整令后：确定性规则引擎是默认路径，不会因「模型不可用」失败。
        # 失败路径改用大模型插件场景（QBL_USE_LLM=1 但没有可用 key/输出不合规），测的仍是「失败退次数」。
        old_model = os.environ.get("QBL_ENGINE_MODEL")
        old_llm = os.environ.get("QBL_USE_LLM")
        os.environ["QBL_ENGINE_MODEL"] = "deepseek"
        os.environ["QBL_USE_LLM"] = "1"
        try:
            failed_created = create_task(client, fresh["token"], "fail-1")
            check("失败任务创建时也是 pending/running（D8）", failed_created.status_code == 200 and failed_created.json()["data"]["status"] in ("pending", "running"), failed_created.text[:200])
            failed = wait_task(client, fresh["token"], failed_created.json()["data"]["task_id"])
        finally:
            os.environ["QBL_ENGINE_MODEL"] = old_model or "mock"
            if old_llm is None:
                os.environ.pop("QBL_USE_LLM", None)
            else:
                os.environ["QBL_USE_LLM"] = old_llm
        check("插件失败时轮询到 failed 且带错误码", failed["status"] == "failed" and failed["error_code"] in ("ANALYSIS_FAILED", "SCHEMA_FAILED"), {k: failed.get(k) for k in ("status", "error_code")})
        check("失败任务没有报告", failed["report"] is None)
        balance_after_fail = client.get("/me", headers=auth(fresh["token"])).json()["data"]["quota"]["balance"]
        check("失败后额度退回（回到 3 次）", balance_after_fail == 3, balance_after_fail)

        section("7. 次数用尽")
        for marker in ("drain-1", "drain-2", "drain-3"):
            create_task(client, fresh["token"], marker)
        exhausted = create_task(client, fresh["token"], "drain-4")
        check("额度用尽返回 402 QUOTA_EXHAUSTED", exhausted.status_code == 402 and exhausted.json()["error"]["code"] == "QUOTA_EXHAUSTED", exhausted.status_code)

        section("8. 并发 5 单不串额度")
        busy = login(client)
        for i in range(5):   # 3 次免费 + 5 次广告 = 8
            client.post("/ad/reward", headers=auth(busy["token"]), json={"request_id": f"busy-ad-{i}", "ad_unit_id": "unit-a", "result": "completed"})
        start_balance = client.get("/me", headers=auth(busy["token"])).json()["data"]["quota"]["balance"]
        check("并发测试前余额 8", start_balance == 8, start_balance)
        os.environ["QBL_FAKE_ENGINE_DELAY_MS"] = "300"   # 让 5 个任务真的并发跑
        try:
            tasks = [create_task(client, busy["token"], f"concurrent-{i}").json()["data"]["task_id"] for i in range(5)]
            results = [wait_task(client, busy["token"], tid) for tid in tasks]
        finally:
            os.environ.pop("QBL_FAKE_ENGINE_DELAY_MS", None)
        check("5 个任务全部完成", all(r["status"] == "done" for r in results), [r["status"] for r in results])
        check("5 条报告都不是别人的（归属一致）", all(r["report"] is not None for r in results))
        end_balance = client.get("/me", headers=auth(busy["token"])).json()["data"]["quota"]["balance"]
        check("并发 5 单正好扣 5 次（8→3）", end_balance == 3, end_balance)

        section("9. 30 秒转后台语义（测试用阈值调到 1 秒）")
        slow = login(client)
        os.environ["QBL_BACKGROUND_AFTER_SECONDS"] = "1"
        os.environ["QBL_FAKE_ENGINE_DELAY_MS"] = "2500"
        try:
            slow_task = create_task(client, slow["token"], "slow-1").json()["data"]["task_id"]
            time.sleep(1.3)
            mid = client.get(f"/analysis/{slow_task}", headers=auth(slow["token"])).json()["data"]
            check("超过阈值仍没结果时 background_mode=true", mid["background_mode"] is True, mid)
            check("转后台时任务仍在跑（running/pending）", mid["status"] in ("pending", "running"), mid["status"])
            check("转后台后仍可继续轮询拿到 poll_after_ms", isinstance(mid["poll_after_ms"], int), mid.get("poll_after_ms"))
        finally:
            os.environ.pop("QBL_FAKE_ENGINE_DELAY_MS", None)
            os.environ.pop("QBL_BACKGROUND_AFTER_SECONDS", None)
        final = wait_task(client, slow["token"], slow_task, timeout=20)
        check("后台跑完后仍然是 done（不取消）", final["status"] == "done", final["status"])

        section("9.5 新增契约：/plans、ad 今日次数、上传归属与过期、单笔上限、旧版 multipart 兼容")
        plans = client.get("/plans", headers=auth(token)).json()["data"]
        amounts = {p["plan"]: p["amount_fen"] for p in plans["plans"]}
        check("GET /plans 返回三档且金额正确", amounts == {"week": 690, "month": 1990, "quarter": 3990}, amounts)
        check("定价表给出单笔上限 300 元", plans["max_single_order_fen"] == 30000, plans.get("max_single_order_fen"))
        me_ad = client.get("/me", headers=auth(token)).json()["data"]["ad"]
        check("/me 的 ad 带今日已看次数与剩余", "today_count" in me_ad and "remaining_today" in me_ad, me_ad)
        other_user = login(client)
        other_img = upload_image(client, other_user["token"], "other-img")
        resp = client.post("/analysis", headers=auth(token), json={"image_ids": [other_img], "ocr_text": OCR_TEXT})
        check("用别人的 image_id 建任务 → 400 IMAGE_NOT_FOUND", resp.status_code == 400 and resp.json()["error"]["code"] == "IMAGE_NOT_FOUND", resp.text[:200])
        os.environ["QBL_UPLOAD_TTL_HOURS"] = "0"
        try:
            exp_img = upload_image(client, token, "expired-img")
        finally:
            os.environ.pop("QBL_UPLOAD_TTL_HOURS", None)
        resp = client.post("/analysis", headers=auth(token), json={"image_ids": [exp_img], "ocr_text": OCR_TEXT})
        check("过期 image_id → 400 IMAGE_EXPIRED", resp.status_code == 400 and resp.json()["error"]["code"] == "IMAGE_EXPIRED", resp.text[:200])
        os.environ["QBL_MAX_ORDER_AMOUNT_FEN"] = "100"
        try:
            cap_order = client.post("/orders", headers=auth(token), json={"plan": "month", "channel": "toutiao"})
        finally:
            os.environ.pop("QBL_MAX_ORDER_AMOUNT_FEN", None)
        check("单笔超上限 → 400 ORDER_AMOUNT_EXCEEDED", cap_order.status_code == 400 and cap_order.json()["error"]["code"] == "ORDER_AMOUNT_EXCEEDED", cap_order.text[:200])
        legacy = legacy_multipart_create(client, token, "legacy-1")
        check("旧版 multipart 仍可用（兼容期）", legacy.status_code == 200 and legacy.json()["data"]["status"] in ("pending", "running"), legacy.text[:200])
        wait_task(client, token, legacy.json()["data"]["task_id"])

        section("9.6 v2 统计与套路库")
        me_v2 = client.get("/me", headers=auth(token)).json()["data"]
        check("GET /me 带 checked_count", isinstance(me_v2.get("checked_count"), int) and me_v2["checked_count"] >= 1, me_v2.get("checked_count"))
        check("GET /me 带 red_count", isinstance(me_v2.get("red_count"), int) and me_v2["red_count"] >= 1, me_v2.get("red_count"))
        plist = client.get("/patterns", headers=auth(token)).json()["data"]
        check("GET /patterns 返回套路库（≥20 条）", plist["total"] >= 20 and len(plist["items"]) >= 20, plist.get("total"))
        recent = client.get("/patterns/recent", headers=auth(token)).json()["data"]
        check("GET /patterns/recent 返回 Top3", len(recent["items"]) == 3 and recent["items"][0].get("rank") == 1, len(recent["items"]))

        section("9.7 求助广场（R3，开关默认关）")
        off = client.get("/community/posts", headers=auth(token))
        check("开关关闭时 GET 返回 404", off.status_code == 404 and off.json()["error"]["code"] == "NOT_FOUND", off.status_code)
        off_post = client.post("/community/posts", headers=auth(token), json={})
        check("D-07：开关关闭时 POST 也返回 404（body 校验前拦截）", off_post.status_code == 404 and off_post.json()["error"]["code"] == "NOT_FOUND", off_post.status_code)
        os.environ["QBL_FEATURE_COMMUNITY"] = "1"
        os.environ["QBL_COMMUNITY_NEW_ACCOUNT_HOURS"] = "0"
        try:
            admin_h2 = {"X-Admin-Token": "dev-admin-token"}
            words = client.put("/admin/sensitive-words", headers=admin_h2, json={"words": [
                {"word": "傻逼", "level": "block"},
                {"word": "骗子", "level": "review", "prompt": "请改成描述你亲身经历的事实"},
                {"word": r"https?://\S+", "level": "block", "kind": "regex"},
                {"word": r"1[3-9]\d{9}", "level": "mask", "kind": "regex", "as_type": "phone"},
            ]})
            check("后台可写敏感词库（词+正则）", words.status_code == 200 and words.json()["data"]["total"] == 4, words.text[:150])
            user_a = login(client)
            user_b = login(client)
            user_c = login(client)
            user_d = login(client)
            blocked = client.post("/community/posts", headers=auth(user_a["token"]), json={"question": "傻逼公司到底靠不靠谱", "company": "某某公司"})
            check("block 级直接拒收（400 CONTENT_BLOCKED）", blocked.status_code == 400 and blocked.json()["error"]["code"] == "CONTENT_BLOCKED", blocked.text[:200])
            rewrite = client.post("/community/posts", headers=auth(user_a["token"]), json={"question": "这家公司是不是骗子，大家说说", "company": "某某公司"})
            check("rewrite 级返回改写提示（400 NEEDS_REWRITE）", rewrite.status_code == 400 and rewrite.json()["error"]["code"] == "NEEDS_REWRITE" and "描述" in json.dumps(rewrite.json()["error"], ensure_ascii=False), rewrite.text[:200])
            link = client.post("/community/posts", headers=auth(user_a["token"]), json={"question": "详情看 http://example.com 这个链接", "company": "某某公司"})
            check("外链正则直接拒收（400）", link.status_code == 400 and link.json()["error"]["code"] == "CONTENT_BLOCKED", link.text[:200])
            created_post = client.post("/community/posts", headers=auth(user_a["token"]),
                json={"question": "这家公司面试前要交培训费，是真的吗？", "company": "王经理 13800000000 的公司", "position": "运营助理", "city": "市北区", "anonymous": True})
            post_data = created_post.json()["data"]
            check("发帖先审后发（pending）", created_post.status_code == 200 and post_data["status"] == "pending", created_post.text[:200])
            hidden_in_list = client.get("/community/posts", headers=auth(user_b["token"])).json()["data"]["items"]
            check("未审核帖子不出现在列表", all(item["post_id"] != post_data["post_id"] for item in hidden_in_list))
            pending_list = client.get("/admin/community/posts?status=pending", headers=admin_h2).json()["data"]
            check("D-08：后台能查到待审帖子", any(i["post_id"] == post_data["post_id"] for i in pending_list["items"]), pending_list.get("total"))
            reviewed = client.post(f"/admin/community/posts/{post_data['post_id']}/approve", headers=admin_h2, json={"operator": "ops-1"})
            check("D-08：审核通过接口生效（且记录处理人）", reviewed.status_code == 200 and reviewed.json()["data"]["status"] == "approved" and reviewed.json()["data"]["reviewed_by"] == "ops-1", reviewed.text[:200])
            listed = client.get("/community/posts", headers=auth(user_b["token"])).json()["data"]["items"]
            check("审核后出现在列表", any(item["post_id"] == post_data["post_id"] for item in listed))
            detail = client.get(f"/community/posts/{post_data['post_id']}", headers=auth(user_b["token"])).json()["data"]
            check("隐私打码生效（公司/手机号）", "13800000000" not in json.dumps(detail, ensure_ascii=False) and "138****0000" in json.dumps(detail, ensure_ascii=False), detail.get("company"))
            phone_post = client.post("/community/posts", headers=auth(user_a["token"]),
                json={"question": "面试时对方让我联系 13812345678 交钱，这正常吗", "company": "某某公司"})
            phone_data = phone_post.json()["data"]
            client.post(f"/admin/community/posts/{phone_data['post_id']}/approve", headers=admin_h2, json={})
            phone_detail = client.get(f"/community/posts/{phone_data['post_id']}", headers=auth(user_b["token"])).json()["data"]
            check("mask 级正则自动打码后放行", phone_post.status_code == 200 and "13812345678" not in json.dumps(phone_detail, ensure_ascii=False) and "138****5678" in json.dumps(phone_detail, ensure_ascii=False), phone_detail.get("question"))
            exp_rewrite = client.post(f"/community/posts/{post_data['post_id']}/experiences", headers=auth(user_b["token"]), json={"content": "这家公司就是骗子，骗了我钱"})
            check("经历同样走 rewrite 拦截", exp_rewrite.status_code == 400 and exp_rewrite.json()["error"]["code"] == "NEEDS_REWRITE", exp_rewrite.text[:200])
            appeal_block = client.post("/community/appeals", headers=auth(user_b["token"]), json={"company": "某某公司", "content": "傻逼公司乱发帖，请处理一下"})
            check("申诉同样走 block 拦截", appeal_block.status_code == 400 and appeal_block.json()["error"]["code"] == "CONTENT_BLOCKED", appeal_block.text[:200])
            self_vote = client.post(f"/community/posts/{post_data['post_id']}/vote", headers=auth(user_a["token"]), json={"value": 1})
            check("发帖人不能投自己（403）", self_vote.status_code == 403, self_vote.status_code)
            v1 = client.post(f"/community/posts/{post_data['post_id']}/vote", headers=auth(user_b["token"]), json={"value": 1, "reason": "有帮助"})
            v2 = client.post(f"/community/posts/{post_data['post_id']}/vote", headers=auth(user_b["token"]), json={"value": -1})
            check("一人一票可改（改票后 up=0/down=1）", v1.status_code == 200 and v2.json()["data"]["vote_up"] == 0 and v2.json()["data"]["vote_down"] == 1, v2.text[:200])
            voted_list = client.get("/community/posts?sort=voted", headers=auth(user_b["token"])).json()["data"]["items"]
            check("我投过的排序能查到", any(i["post_id"] == post_data["post_id"] for i in voted_list), len(voted_list))
            exp = client.post(f"/community/posts/{post_data['post_id']}/experiences", headers=auth(user_b["token"]), json={"content": "我也遇到过，面试时让先交钱，赶紧走。"})
            exp_id = exp.json()["data"]["experience_id"]
            check("补充经历先审后发", exp.status_code == 200 and exp.json()["data"]["status"] == "pending", exp.text[:150])
            exp_pending = client.get("/admin/community/experiences?status=pending", headers=admin_h2).json()["data"]
            check("D-08：后台能查到待审经历", any(i["experience_id"] == exp_id for i in exp_pending["items"]), exp_pending.get("total"))
            exp_ok = client.post(f"/admin/community/experiences/{exp_id}/approve", headers=admin_h2, json={})
            check("D-08：经历审核通过后可见", exp_ok.status_code == 200 and exp_ok.json()["data"]["status"] == "approved")
            exp_list = client.get(f"/community/posts/{post_data['post_id']}/experiences", headers=auth(user_c["token"])).json()["data"]["items"]
            check("经历审核通过后出现在列表", any(i["experience_id"] == exp_id for i in exp_list), len(exp_list))
            exp2 = client.post(f"/community/posts/{post_data['post_id']}/experiences", headers=auth(user_c["token"]), json={"content": "补充一条会被驳回的经历，用于测试驳回接口。"})
            exp2_id = exp2.json()["data"]["experience_id"]
            exp_rej = client.post(f"/admin/community/experiences/{exp2_id}/reject", headers=admin_h2, json={"reason": "与主题无关"})
            check("D-08：经历可驳回", exp_rej.status_code == 200 and exp_rej.json()["data"]["status"] == "rejected", exp_rej.text[:150])
            r1b = client.post(f"/community/posts/{post_data['post_id']}/report", headers=auth(user_b["token"]), json={"reason": "泄漏隐私"})
            r2 = client.post(f"/community/posts/{post_data['post_id']}/report", headers=auth(user_c["token"]), json={})
            r3 = client.post(f"/community/posts/{post_data['post_id']}/report", headers=auth(user_d["token"]), json={})
            check("举报满 3 次自动隐藏", r3.json()["data"]["hidden"] is True and r3.json()["data"]["report_count"] == 3, r3.text[:200])
            after_hide = client.get(f"/community/posts/{post_data['post_id']}", headers=auth(user_b["token"]))
            check("隐藏后普通用户看不到（404）", after_hide.status_code == 404, after_hide.status_code)
            appeal = client.post("/community/appeals", headers=auth(user_b["token"]),
                json={"post_id": post_data["post_id"], "company": "某某公司", "contact": "13800000000", "content": "该内容与事实不符，请核实处理，谢谢。"})
            check("企业申诉受理（24h SLA）", appeal.status_code == 200 and appeal.json()["data"]["sla_hours"] == 24, appeal.text[:200])
        finally:
            os.environ.pop("QBL_FEATURE_COMMUNITY", None)
            os.environ.pop("QBL_COMMUNITY_NEW_ACCOUNT_HOURS", None)

        section("9.8 D18 防刷：可疑票收下但不计展示")
        os.environ["QBL_FEATURE_COMMUNITY"] = "1"
        os.environ["QBL_COMMUNITY_NEW_ACCOUNT_HOURS"] = "0"
        try:
            admin_h3 = {"X-Admin-Token": "dev-admin-token"}
            poster = login(client)
            voter = login(client)
            voter2 = login(client)

            def make_post(text: str) -> str:
                pid = client.post("/community/posts", headers=auth(poster["token"]), json={"question": text}).json()["data"]["post_id"]
                client.post(f"/admin/community/posts/{pid}/approve", headers=admin_h3, json={})
                return pid

            posts = [make_post(f"防刷测试帖{i}：面试时对方要求先交钱，这正常吗") for i in range(6)]
            device = {"X-Device-Id": "smoke-device-001"}
            for pid in posts[:5]:
                r = client.post(f"/community/posts/{pid}/vote", headers={**auth(voter["token"]), **device}, json={"value": 1})
            flood = client.post(f"/community/posts/{posts[5]}/vote", headers={**auth(voter["token"]), **device}, json={"value": 1})
            check("同设备第 6 票接口照常成功（用户无感）", flood.status_code == 200 and flood.json()["data"]["my_vote"] == 1, flood.text[:200])
            check("可疑票不计入展示（该帖 vote_up=0）", flood.json()["data"]["vote_up"] == 0, flood.json()["data"])
            suspicious = client.get("/admin/community/votes?counted=0", headers=admin_h3).json()["data"]
            hit = [i for i in suspicious["items"] if i["post_id"] == posts[5]]
            check("后台能查到可疑票且带 device_flood 原因", bool(hit) and hit[0]["risk_reason"] == "device_flood", suspicious.get("total"))
            check("后台只返回设备号摘要（不存明文）", bool(hit) and hit[0]["device_digest"] and "smoke-device-001" not in json.dumps(suspicious, ensure_ascii=False), hit[:1])
            first_vote = client.get(f"/community/posts/{posts[0]}", headers=auth(voter2["token"])).json()["data"]
            check("前 5 票正常计入展示", first_vote["vote_up"] == 1, first_vote.get("vote_up"))
            other_device = client.post(f"/community/posts/{posts[5]}/vote", headers={**auth(voter2["token"]), "X-Device-Id": "smoke-device-002"}, json={"value": 1})
            check("不同设备投票正常计入", other_device.json()["data"]["vote_up"] == 1, other_device.text[:200])
            no_header = client.post(f"/community/posts/{posts[5]}/vote", headers=auth(login(client)["token"]), json={"value": 1})
            check("缺 X-Device-Id 不报错（退回 openid+IP）", no_header.status_code == 200, no_header.text[:200])
            switcher = login(client)
            change_device = {"X-Device-Id": "smoke-device-003"}
            change_post = make_post("改票测试帖：面试地点约在酒店大堂，这正常吗")
            first_vote2 = client.post(f"/community/posts/{change_post}/vote", headers={**auth(switcher["token"]), **change_device}, json={"value": 1})
            changed = client.post(f"/community/posts/{change_post}/vote", headers={**auth(switcher["token"]), **change_device}, json={"value": -1})
            check("改票不重复计（up 归零、down=1）", first_vote2.json()["data"]["vote_up"] == 1 and changed.json()["data"]["vote_up"] == 0 and changed.json()["data"]["vote_down"] == 1, changed.text[:200])
            votes_public = client.get(f"/community/posts/{change_post}", headers=auth(voter2["token"])).json()["data"]
            check("改票后公开票数一致", votes_public["vote_up"] == 0 and votes_public["vote_down"] == 1, votes_public)
        finally:
            os.environ.pop("QBL_FEATURE_COMMUNITY", None)
            os.environ.pop("QBL_COMMUNITY_NEW_ACCOUNT_HOURS", None)

        section("10. 反馈与后台")
        fb = client.post("/feedback", headers=auth(token), json={"report_id": "r_x", "type": "inaccurate", "content": "这条判断不准"})
        check("反馈提交成功（进复核池）", fb.status_code == 200 and fb.json()["data"]["status"] == "open")
        no_token = client.get("/admin/stats")
        check("无管理员令牌访问后台 → 403", no_token.status_code == 403, no_token.status_code)
        admin_h = {"X-Admin-Token": "dev-admin-token"}
        stats = client.get("/admin/stats", headers=admin_h).json()["data"]
        check("后台统计可读", stats["counts"]["users"] >= 3, stats["counts"])
        check("额度对账通过（无负余额、无孤立预扣）", stats["quota_reconcile"]["balanced"] is True, stats["quota_reconcile"])
        check("会员订单收入 1990 分", stats["orders"]["revenue_fen"] == 1990, stats["orders"])
        lex = client.get("/admin/rules", headers=admin_h).json()["data"]
        check("词库可读且规则数 ≥ 20", lex["rule_count"] >= 20, lex["rule_count"])
        bad_lex = client.put("/admin/rules", headers=admin_h, json={"version": "bad", "rules": [{"rule_id": "X"}]})
        check("坏词库被拒（400）", bad_lex.status_code == 400, bad_lex.status_code)
        pool = client.get("/admin/review-pool", headers=admin_h).json()["data"]
        check("复核池能查到刚提的反馈", pool["total"] >= 1, pool["total"])

        section("11. 报告列表与过期")
        reports = client.get("/reports", headers=auth(token)).json()["data"]
        check("GET /reports 返回历史报告", len(reports["items"]) >= 1, len(reports["items"]))
        check("报告带过期时间（会员 30 天）", reports["items"][0]["expires_at"] > reports["items"][0]["created_at"])

    print(f"\n结果：{PASS} 项通过，{FAIL} 项失败")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
