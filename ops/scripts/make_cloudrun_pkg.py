"""生成云托管部署包（只含运行时必需文件）。

为什么需要：整个项目目录约 40 MB（tests 17MB / data 7.5MB / var 7.5MB / reports 4.1MB），
手动上传整个文件夹会把测试集、报告、日志一并传上去——体积大、可能超云托管限制、
而且 var/ 里还有本地日志与数据库。这里只打运行时真正需要的：

    Dockerfile  requirements.txt  backend/  engine/  rules/

用法：
    python ops/scripts/make_cloudrun_pkg.py
    -> 产出 ops/dist/qbl-cloudrun-<时间戳>/ 目录（上传这个目录即可）
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OPS = ROOT / "ops"
DIST = OPS / "dist"

# 运行时必需（对应 ops/Dockerfile.cloudrun 里的 COPY 指令）
INCLUDE_DIRS = ["backend", "engine", "rules"]
INCLUDE_FILES = ["requirements.txt", "backend/requirements.txt"]
# 部署当天要在容器里跑的性能自检脚本（见 ops/evidence/ocr-cloudrun-baseline.md §4）
# 不进这个包，云上就无法复测 21 张基线，D40 验收线验证不了。
EXTRA_FILES = ["ops/scripts/ocr_baseline_21.py"]
# 运行时必须排除的（即使在上面的目录里）
EXCLUDE_PATTERNS = ["__pycache__", "*.pyc", "*.pyo", ".pytest_cache"]

DOCKERFILE_SRC = OPS / "Dockerfile.cloudrun"


def _ignore(_dir: str, names: list[str]) -> set[str]:
    import fnmatch

    dropped = set()
    for n in names:
        if any(fnmatch.fnmatch(n, pat) for pat in EXCLUDE_PATTERNS):
            dropped.add(n)
    return dropped


def main() -> int:
    if not DOCKERFILE_SRC.exists():
        print(f"[pkg] 找不到 {DOCKERFILE_SRC}")
        return 1

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = DIST / f"qbl-cloudrun-{stamp}"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # Dockerfile 放根目录，并改名
    shutil.copy2(DOCKERFILE_SRC, out / "Dockerfile")

    for f in INCLUDE_FILES:
        src = ROOT / f
        if not src.exists():
            print(f"[pkg] 缺少必需文件：{f}")
            return 1
        dest = out / f
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    for d in INCLUDE_DIRS:
        src = ROOT / d
        if not src.exists():
            print(f"[pkg] 缺少必需目录：{d}")
            return 1
        shutil.copytree(src, out / d, ignore=_ignore, dirs_exist_ok=True)

    # 额外的运行/自检脚本（保持原始相对路径，如 ops/scripts/xxx.py）
    for f in EXTRA_FILES:
        src = ROOT / f
        if not src.exists():
            print(f"[pkg] 警告：缺少附带脚本 {f}（部署当天将无法在云上跑基线）")
            continue
        dest = out / f
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    # 安全自检：不许带进密钥与数据
    leaked = []
    for pat in (".env", "*.db", "*.log", "*.pem", "*.key"):
        leaked.extend(p.name for p in out.rglob(pat))
    if leaked:
        print(f"[pkg] ❌ 包里混进了不该有的文件：{leaked[:10]}")
        return 1

    files = [p for p in out.rglob("*") if p.is_file()]
    total = sum(p.stat().st_size for p in files)
    print(f"[pkg] 输出目录：{out}")
    print(f"[pkg] 文件数  ：{len(files)}")
    print(f"[pkg] 总大小  ：{total / 1024 / 1024:.2f} MB")
    print("[pkg] 上传方式：云托管控制台 → 部署发布 → 手动上传代码包 → 选「文件夹」→ 选上面的目录")
    print("[pkg] 安全自检：未包含 .env / *.db / *.log / 证书，通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
