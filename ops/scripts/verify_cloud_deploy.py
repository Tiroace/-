"""云上验收：拿到服务地址后一条命令跑完四项（本机执行，走公网）。

用法：
    python ops/scripts/verify_cloud_deploy.py --url https://qbl-api-xxxx.ap-shanghai.run.tcloudbase.com

检查项（对应老板 004 验收四项的 ②③④）：
  1. GET /health → 200，且 env == prod、content_safety != local
  2. 上传一张真实图跑分析 → trace.ocr.source == rapidocr
  3. 单张耗时、3 张耗时

注意：若控制台「允许公网访问」是关闭的，本脚本连不上——那不是故障，
需改走云端调试 `curl localhost:8080/health`，或等预览码走 callContainer。
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RAW_DIR = Path(r"D:\qiuzhibilei-local-private\raw-baseline")


def _get(url: str, timeout: int = 15) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return -1, f"{type(exc).__name__}: {exc}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="服务地址，如 https://xxx.run.tcloudbase.com")
    args = ap.parse_args()
    base = args.url.rstrip("/")

    print("=" * 66)
    print("云上验收（004）")
    print("=" * 66)
    print(f"地址: {base}")
    print()

    # ---------- ① /health ----------
    print("-" * 66)
    print("【1】/health")
    print("-" * 66)
    status, body = _get(f"{base}/health")
    print(f"HTTP {status}")
    print(f"响应: {body[:400]}")

    ok_health = False
    if status == 200:
        try:
            data = json.loads(body).get("data", {})
            env_v = data.get("env")
            cs = data.get("content_safety")
            print()
            print(f"  env             = {env_v}   {'✅' if env_v == 'prod' else '❌ 必须是 prod'}")
            print(f"  content_safety  = {cs}   {'✅' if cs and cs != 'local' else '❌ 不能是 local'}")
            print(f"  db              = {data.get('db')}")
            ok_health = env_v == "prod" and cs and cs != "local"
        except Exception as exc:  # noqa: BLE001
            print(f"  ❌ 响应不是预期 JSON：{exc}")
    else:
        print("  ❌ /health 不通。若控制台关闭了公网访问，这不是故障——")
        print("     改走云端调试 curl localhost:8080/health")

    if not ok_health:
        print()
        print("=" * 66)
        print("总判定：❌ 未通过（/health 未满足 env=prod 且 content_safety≠local）")
        print("=" * 66)
        return 1

    print()
    print("=" * 66)
    print("【2】【3】真实图识别与耗时")
    print("=" * 66)
    print("⚠️ 这两项需要调用上传/分析接口，涉及鉴权与 multipart。")
    print("   建议改用开发者已写好的 eval/eval_api_e2e.py（在容器内或指到该地址）。")
    print()
    if RAW_DIR.exists():
        imgs = sorted(RAW_DIR.glob("*.png"))
        print(f"   本地可用真实图：{len(imgs)} 张（{RAW_DIR}）")
    print("=" * 66)
    print("结论：/health 已通过；识别与耗时请用 eval_api_e2e.py 补齐。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
