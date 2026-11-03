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
# 不进这个包，云上就无法复测 21 张基线与 D40 端到端验收。
EXTRA_FILES = [
    "ops/scripts/ocr_baseline_21.py",
    # D40 端到端验收（21 张真实图 + 7 组三图，走真实 API），开发者第 2 关交付
    "eval/eval_api_e2e.py",
    "eval/_console.py",
]
# 验收用的真实图片。eval_api_e2e.py 与 ocr_baseline_21.py 都按 data/testset/_raw 找图，
# 容器里没有这个目录就跑不了验收，所以直接把图片打进包（约 7.5MB，可接受）。
INCLUDE_IMAGE_DIRS = ["data/testset/_raw"]
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
    import argparse

    ap = argparse.ArgumentParser(description="生成云托管部署包")
    ap.add_argument("--allow-dirty", action="store_true",
                    help="运行时代码有未提交改动时仍然生成包（自担风险，通常用于本地调试）")
    args = ap.parse_args()

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
            print(f"[pkg] 警告：缺少附带脚本 {f}（部署当天将无法在云上跑验收）")
            continue
        dest = out / f
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    # 验收图片（保持 data/testset/_raw 相对路径，脚本按这个位置找图）
    for d in INCLUDE_IMAGE_DIRS:
        src = ROOT / d
        if not src.exists():
            print(f"[pkg] 警告：缺少验收图片目录 {d}（云上将跑不了 D40 端到端验收）")
            continue
        shutil.copytree(src, out / d, dirs_exist_ok=True)

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

    # ---------- 版本校验（防止部署半成品）----------
    head, dirty_lines = _check_git_state()
    _write_package_info(out, head, dirty_lines, len(files), total)

    if dirty_lines:
        if args.allow_dirty:
            print("")
            print("[pkg] ⚠️  --allow-dirty：已生成包，但**内容含未提交改动，不要用于正式部署**。")
            return 0
        print("")
        print("[pkg] ❌ 打包中止：运行时代码有未提交改动，拒绝生成可用于部署的包。")
        print("[pkg]    请先提交并跑测试通过，再重新打包。")
        print("[pkg]    确实要用当前工作区内容时，加 --allow-dirty 显式承担风险。")
        return 1
    return 0


def _check_git_state() -> tuple[str, list[str]]:
    """返回 (HEAD 短 commit, 未提交的运行时改动行)。

    踩过的坑：开发者正在改 analysis.py（旁路加固）时打了包，
    包里是改动一半的代码，部署上去行为不可预期。
    """
    import subprocess

    def run(args: list[str]) -> str:
        try:
            return subprocess.run(["git", *args], cwd=str(ROOT),
                                  capture_output=True, text=True, timeout=15).stdout.strip()
        except Exception:  # noqa: BLE001
            return ""

    head = run(["rev-parse", "--short", "HEAD"])
    dirty = run(["status", "--porcelain", "--", "backend", "engine", "rules"])
    dirty_lines = [ln for ln in dirty.splitlines() if ln.strip()]

    print("")
    print("[pkg] ---- 版本校验 ----")
    if head:
        print(f"[pkg] 打包基线 commit: {head}")
    if dirty_lines:
        print("[pkg] ⚠️  以下运行时代码有**未提交改动**（可能是半成品）：")
        for line in dirty_lines[:10]:
            print(f"[pkg]     {line}")
    else:
        print("[pkg] ✅ 运行时代码无未提交改动，包内容 = HEAD 版本")
    return head, dirty_lines


def _write_package_info(out: Path, head: str, dirty: list[str],
                        n_files: int, total: int) -> None:
    """把版本信息写进包，事后能查出「这次部署的是哪一版」。"""
    from datetime import datetime

    lines = [
        "云托管部署包信息",
        "=" * 40,
        f"打包时间   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"基线 commit: {head or '未知'}",
        f"文件数     : {n_files}",
        f"总大小     : {total / 1024 / 1024:.2f} MB",
        f"代码状态   : {'干净（= HEAD 版本）' if not dirty else '有未提交改动（半成品，勿部署）'}",
    ]
    if dirty:
        lines.append("未提交改动：")
        lines.extend(f"  {ln}" for ln in dirty)
    (out / "PACKAGE_INFO.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
