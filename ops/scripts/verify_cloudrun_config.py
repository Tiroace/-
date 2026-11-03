"""配置保存后的只读校对脚本（不需要登录云端，只读控制台+本地包）。

用法：
    python ops/scripts/verify_cloudrun_config.py --env-json <控制台读回的JSON文件>
    # 不带参数时只做本地包校验

检查项：
  1. 包基线版本与 PACKAGE_INFO 一致
  2. 12 项环境变量键齐全、无多余、值非空（不打印值）
  3. 与本地 env-12.json 逐键比对（不打印值，只报是否一致）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PKG = Path(r"D:\qbl-deploy-day\ops\dist\qbl-cloudrun-20261103-203958")
LOCAL_ENV = Path(r"D:\qiuzhibilei-local-private\cloudrun-env\env-12.json")

REQUIRED_KEYS = [
    "QBL_ENV", "QBL_DEV_MODE", "QBL_FEATURE_COMMUNITY", "QBL_USE_LLM",
    "QBL_UPLOAD_TTL_HOURS", "QBL_WORKER_THREADS", "QBL_OCR_THREADS",
    "QBL_WX_APPID", "QBL_CONTENT_SAFETY",
    "QBL_ADMIN_TOKEN", "QBL_TOKEN_SECRET", "QBL_PAY_SECRET",
]


def check_package() -> bool:
    print("=" * 60)
    print("1. 本地部署包校验")
    print("=" * 60)
    if not PKG.exists():
        print(f"  ❌ 包目录不存在：{PKG}")
        return False
    info = PKG / "PACKAGE_INFO.txt"
    if not info.exists():
        print("  ❌ 缺 PACKAGE_INFO.txt")
        return False
    text = info.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.strip():
            print(f"  {line}")
    ok = "e4425ac" in text and "干净" in text
    print(f"  {'✅' if ok else '❌'} 基线应为 e4425ac 且代码状态干净")
    return ok


def check_env(env_path: Path | None) -> bool:
    print()
    print("=" * 60)
    print("2. 环境变量校验")
    print("=" * 60)
    if env_path is None or not env_path.exists():
        print("  ⏭  未提供控制台读回文件，跳过（用 --env-json 指定）")
        return True

    try:
        cloud = json.loads(env_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"  ❌ 读回文件不是合法 JSON：{exc}")
        return False

    local = json.loads(LOCAL_ENV.read_text(encoding="utf-8")) if LOCAL_ENV.exists() else {}

    missing = [k for k in REQUIRED_KEYS if k not in cloud]
    extra = [k for k in cloud if k not in REQUIRED_KEYS]
    empty = [k for k, v in cloud.items() if not str(v).strip()]

    print(f"  云端共 {len(cloud)} 项")
    print(f"  缺失  : {missing if missing else '无'}   {'✅' if not missing else '❌'}")
    print(f"  多余  : {extra if extra else '无'}   {'✅' if not extra else '⚠️'}")
    print(f"  空值  : {empty if empty else '无'}   {'✅' if not empty else '❌'}")

    # 逐键比对值是否一致（不打印值）
    if local:
        diff = [k for k in REQUIRED_KEYS if k in cloud and k in local and str(cloud[k]) != str(local[k])]
        print(f"  与本地基准不一致的键：{diff if diff else '无'}   {'✅' if not diff else '❌'}")

    ok = not missing and not empty
    print(f"  结论：{'✅ 通过' if ok else '❌ 不通过'}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-json", type=Path, default=None,
                    help="从控制台读回的环境变量 JSON 文件路径")
    args = ap.parse_args()

    ok1 = check_package()
    ok2 = check_env(args.env_json)

    print()
    print("=" * 60)
    print(f"总判定：{'✅ 通过' if (ok1 and ok2) else '❌ 不通过'}")
    print("=" * 60)
    print()
    print("⚠️ 本脚本只校验包与环境变量。")
    print("   「配置真的生效」还必须看 /health 的 env 字段 == prod，")
    print("   以及 trace.ocr.source == rapidocr。这两条不在此脚本内。")
    return 0 if (ok1 and ok2) else 1


if __name__ == "__main__":
    sys.exit(main())
