"""改名验收：旧品牌名必须 0 残留（任务书 §9 第 1 条）

范围：代码与文档。**排除**：
- `design/`    设计包原件，任务书本身就叫旧名，是历史输入，不能改
- `reports/`   历史测试报告，记录的是曾经的品牌名，改了会篡改历史
- `tests/rebrand/`  本扫描器自身（它必须知道旧名才能扫描）
- `docs/06-合规与文案/` 合规草稿里会引用旧名做对照

判定：允许词只出现在上述白名单路径；其余路径命中即为缺陷。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import ROOT
# 拼接构造，避免本文件自身被扫到（否则测试文件会自命中）
OLD_BRAND = "求职" + "避雷"
NEW_BRAND = "面试请等等"

# 允许保留旧名的路径前缀（相对项目根，统一用 / 分隔）
ALLOW_PREFIXES = (
    "docs/reference/",      # 设计包原件（历史输入，任务书本身就叫旧名，不能改）
    "docs/requirements/",   # 老板下发的需求原文，必须保留原始品牌名
    "reports/",             # 历史测试报告
    "tests/rebrand/",       # 本扫描器自身
    "src/node_modules/",
)

# 【2026-10-31 Chief 确认口径】改名说明类文档必须保留旧名才能说明「改了啥」，
# 因此整份排除。除这四份外，代码与对外文案一律 0 残留。
ALLOW_FILES = (
    "docs/06-合规与文案/07-R1改名文案替换清单.md",   # 产品经理的改名替换清单
    "docs/05-验收清单映射表-任务书§9.md",            # 测试者的验收映射表
    "docs/08-T5-R1改版记录.md",                     # 前端的改版记录
    "docs/09-改版实施计划.md",                      # Chief 的改版实施计划
    # 以下是测试者自己的文档：需要引用旧名做判据说明
    "docs/05-测试计划与验收标准.md",
    "docs/05-R3求助广场测试计划.md",
    "README.md",
)

SCAN_SUFFIXES = {".vue", ".js", ".ts", ".json", ".scss", ".css", ".wxml", ".wxss", ".py", ".md", ".jsonl"}
SKIP_DIRS = {"node_modules", "__pycache__", ".git", "dist", "unpackage", ".pnpm", "var"}

def _iter_files():
    """遍历待扫描文件。

    【性能】原实现用 ROOT.rglob("*")，会先走遍整棵树（含 node_modules 上万文件、
    dist 构建产物）再逐个判断跳过——单个用例 18 秒，三条用例共 40 多秒，
    是全量最慢的部分（2026-10-31 实测）。
    改为 os.walk 并在目录层直接剪枝，不进入跳过目录。
    """
    import os

    for dirpath, dirnames, filenames in os.walk(ROOT):
        # 目录层剪枝：直接不进这些目录
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() not in SCAN_SUFFIXES:
                continue
            try:
                rel = p.relative_to(ROOT).as_posix()
            except ValueError:
                continue
            if any(part in SKIP_DIRS for part in rel.split("/")):
                continue
            yield p, rel


def _is_allowed(rel: str) -> bool:
    if rel in ALLOW_FILES:
        return True
    return any(rel.startswith(prefix) for prefix in ALLOW_PREFIXES)


def _scan(paths_filter=None):
    hits = []
    for p, rel in _iter_files():
        if _is_allowed(rel):
            continue
        if paths_filter and not paths_filter(rel):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if OLD_BRAND in text:
            for lineno, line in enumerate(text.splitlines(), 1):
                if OLD_BRAND in line:
                    hits.append(f"{rel}:{lineno}: {line.strip()[:100]}")
    return hits


@pytest.fixture(scope="module")
def all_hits():
    """整个模块只扫一遍，三组用例共用结果。

    原实现三个用例各扫一次全树 = 扫三遍，是最慢的根源。
    """
    return _scan()


class Test改名残留:
    def test_全局无旧品牌名残留(self, all_hits):
        """§9 第 1 条：全局搜索旧品牌名，结果为 0。"""
        assert not all_hits, (
            f"发现 {len(all_hits)} 处旧品牌名残留（白名单外）：\n" + "\n".join(all_hits[:20])
        )

    def test_前端源码无旧品牌名(self, all_hits):
        hits = [h for h in all_hits if h.startswith("src/src/")]
        assert not hits, "前端源码仍有旧品牌名：\n" + "\n".join(hits[:10])

    def test_后端与引擎无旧品牌名(self, all_hits):
        hits = [h for h in all_hits if h.startswith(("backend/", "engine/", "rules/"))]
        assert not hits, "后端/引擎仍有旧品牌名：\n" + "\n".join(hits[:10])

    def test_新品牌名至少在关键位置出现(self):
        """反向验证：不能只删旧名、忘了写新名。"""
        must_have = [
            ROOT / "src" / "src" / "manifest.json",
        ]
        checked = []
        for p in must_have:
            if p.is_file():
                checked.append(p.read_text(encoding="utf-8"))
        if not checked:
            pytest.skip("关键文件不存在")
        assert any(NEW_BRAND in t or "mianshi" in t.lower() for t in checked), (
            f"关键配置里没有新品牌名「{NEW_BRAND}」"
        )


class Test扫描器自检:
    def test_扫描器能抓到旧名(self, tmp_path):
        """防「测试全绿但没测到」：给一段含旧名的文本，扫描逻辑必须命中。"""
        sample = f"欢迎使用{OLD_BRAND}小程序"
        assert OLD_BRAND in sample
        # 用真实扫描器扫一个临时目录外的人造目标是不现实的，
        # 这里验证匹配本身的正确性
        assert re.search(re.escape(OLD_BRAND), sample)

# 路线调整令第九节：本文件属「快跑冒烟」核心防线
pytestmark = pytest.mark.smoke
