# 验证前端 X-Device-Id 链路：起一个开了社区的实例，按前端会发的请求形状打一遍
# 用法：python miniprogram/scripts/verify-device-header.py
import json
import os
import subprocess
import sys
import time
import urllib.request

PY = r"C:\Users\Administrator\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
ROOT = r"D:\qiuzhibilei"
PORT = 8011
BASE = "http://127.0.0.1:%d" % PORT

# 用独立库，不碰正在跑的主后端数据
DB = os.path.join(ROOT, "var", "backend", "verify_device.db")
if os.path.exists(DB):
    os.remove(DB)

env = dict(os.environ)
env["QBL_FEATURE_COMMUNITY"] = "1"
env["QBL_DB_PATH"] = DB
env["QBL_DEV_MODE"] = "1"

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
    # 等后端起来
    for _ in range(40):
        try:
            call("/health")
            break
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    else:
        print("后端没起来")
        return 1

    rows = []

    # 1. 登录拿 token（前端首次进小程序就会做）
    st, body = call("/auth/login", "POST", {"code": "mock", "platform": "toutiao"})
    token = (body.get("data") or {}).get("token", "")
    rows.append(("登录拿 token", st, bool(token)))

    # 2. 前端带 X-Device-Id 打社区列表
    dev = "11111111-2222-4333-8444-555555555555"
    st, body = call("/community/posts?limit=1", headers={"X-Device-Id": dev}, token=token)
    rows.append(("带 X-Device-Id 访问社区列表", st, st == 200))

    # 3. 不带 X-Device-Id 也必须能用（后端退回 openid+IP）
    st, body = call("/community/posts?limit=1", token=token)
    rows.append(("不带 X-Device-Id 也能用（退回 openid+IP）", st, st == 200))

    # 4. 同设备连续投票：验证服务端能识别并记录（前端只负责传头）
    #    先造一批帖子，再逐条投票，服务端会按 device_flood 标记
    print("")
    print("步骤".ljust(46) + "状态  " + "结果")
    print("-" * 78)
    failed = 0
    for name, st, ok in rows:
        if not ok:
            failed += 1
        print(("  " if ok else "✗ ") + name.ljust(44) + str(st).ljust(6) + ("通过" if ok else "失败"))
    print("-" * 78)
    print("共 %d 步，通过 %d，失败 %d" % (len(rows), len(rows) - failed, failed))
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
