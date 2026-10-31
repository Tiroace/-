# 验证投票请求头 X-Device-Id 真的进了数据库（device_hash），不是「没报错就算过」
# 用法：python miniprogram/scripts/verify-device-vote.py
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

PY = r"C:\Users\Administrator\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
ROOT = r"D:\qiuzhibilei"
PORT = 8012
BASE = "http://127.0.0.1:%d" % PORT
DB = os.path.join(ROOT, "var", "backend", "verify_vote.db")
if os.path.exists(DB):
    os.remove(DB)

env = dict(os.environ)
env["QBL_FEATURE_COMMUNITY"] = "1"
env["QBL_DB_PATH"] = DB
env["QBL_DEV_MODE"] = "1"
env["QBL_ADMIN_TOKEN"] = "test-admin"
# 新账号 24 小时限制是防刷规则，本身没错；验证设备号链路时先把它关掉（配置可调，见 docs/10）
env["QBL_COMMUNITY_NEW_ACCOUNT_HOURS"] = "0"

proc = subprocess.Popen(
    [PY, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", str(PORT)],
    cwd=ROOT,
    env=env,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)


def call(path, method="GET", body=None, headers=None, token=""):
    h = {"content-type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    if headers:
        h.update(headers)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def main():
    for _ in range(40):
        try:
            call("/health")
            break
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    else:
        print("后端没起来")
        return 1

    results = []

    def check(name, cond, detail=""):
        results.append((name, cond, detail))

    # 1. 登录两个账号
    _, b1 = call("/auth/login", "POST", {"code": "mock:alice", "platform": "toutiao"})
    t1 = (b1.get("data") or {}).get("token", "")
    _, b2 = call("/auth/login", "POST", {"code": "mock:bob", "platform": "toutiao"})
    t2 = (b2.get("data") or {}).get("token", "")
    check("两个账号登录成功", bool(t1 and t2))

    # 2. alice 发帖
    st, body = call(
        "/community/posts",
        "POST",
        {"company": "某测试公司", "position": "测试岗", "city": "测试市", "question": "这个岗位要求先交押金，正常吗？", "anonymous": True},
        token=t1,
    )
    # 契约（docs/10）返回字段是 post_id
    data = body.get("data") or {}
    post_id = data.get("post_id") or data.get("id") or ""
    check("发帖成功", st == 200 and bool(post_id), "post_id=%s" % post_id)

    # 3. 后台审核放行
    st, _ = call(
        "/admin/community/posts/%s/review" % post_id,
        "POST",
        {"action": "approve"},
        headers={"X-Admin-Token": "test-admin"},
    )
    check("后台审核放行", st == 200, "status=%s" % st)

    # 4. 关键一步：bob 带 X-Device-Id 投票
    dev = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    st, body = call(
        "/community/posts/%s/vote" % post_id,
        "POST",
        {"value": 1, "reason": "normal"},
        headers={"X-Device-Id": dev},
        token=t2,
    )
    check("带 X-Device-Id 投票成功", st == 200, "status=%s" % st)

    # 5. 直接查库：device_hash 必须存在且不是空
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM votes ORDER BY created_at DESC LIMIT 1").fetchone()
    cols = list(row.keys()) if row else []
    has_device_col = "device_hash" in cols
    dev_hash = (row["device_hash"] if row and has_device_col else "") or ""
    check("votes 表有 device_hash 列", has_device_col, "列数=%d" % len(cols))
    check("投票记录了设备号哈希（非空）", bool(dev_hash), "device_hash=%s" % dev_hash[:16])
    # 不能存明文设备号（合规）
    check("没有存明文设备号", dev not in str(dict(row)) if row else True)

    # 6. 不带 X-Device-Id 投票也不能报错（后端退回 openid+IP）
    st, body = call(
        "/community/posts/%s/vote" % post_id,
        "POST",
        {"value": -1, "reason": "other"},
        token=t2,
    )
    check("不带 X-Device-Id 投票不报错", st == 200, "status=%s" % st)

    conn.close()

    print("")
    print("检查项".ljust(40) + "结果")
    print("-" * 60)
    failed = 0
    for name, cond, detail in results:
        if not cond:
            failed += 1
        print(("  " if cond else "✗ ") + name.ljust(38) + ("通过" if cond else "失败") + ("  " + detail if detail else ""))
    print("-" * 60)
    print("共 %d 项，通过 %d，失败 %d" % (len(results), len(results) - failed, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            proc.kill()
    sys.exit(code)
